import datetime as dt
import urllib.parse
from typing import Dict, Union

from utils.database import tibiaDatabase
from utils.general import get_local_timezone
from utils.tibia import get_tibia_time_zone

WIKI_ICON = "https://vignette.wikia.nocookie.net/tibia/images/b/bc/Wiki.png/revision/latest?path-prefix=en"


def get_article_url(title: str) -> str:
    return f"http://tibia.wikia.com/wiki/{urllib.parse.quote(title)}"


def get_monster(name):
    """Returns a dictionary with a monster's info, if no exact match was found, it returns a list of suggestions.

    The dictionary has the following keys: name, id, hp, exp, maxdmg, elem_physical, elem_holy,
    elem_death, elem_fire, elem_energy, elem_ice, elem_earth, elem_drown, elem_lifedrain, senseinvis,
    arm, image."""

    # Reading monster database
    c = tibiaDatabase.cursor()
    c.execute("SELECT * FROM creatures WHERE title LIKE ? ORDER BY LENGTH(title) ASC LIMIT 15", ("%" + name + "%",))
    result = c.fetchall()
    if len(result) == 0:
        return None
    elif result[0]["title"].lower() == name.lower() or len(result) == 1:
        monster = result[0]
    else:
        return [x['title'] for x in result]
    try:
        if monster['hitpoints'] is None or monster['hitpoints'] < 1:
            monster['hitpoints'] = None
        c.execute("SELECT items.title as item, chance, min, max "
                  "FROM creatures_drops, items "
                  "WHERE items.id = creatures_drops.item_id AND creature_id = ? "
                  "ORDER BY chance DESC",
                  (monster["id"],))
        monster["loot"] = c.fetchall()
        return monster
    finally:
        c.close()


def get_item(name):
    """Returns a dictionary containing an item's info, if no exact match was found, it returns a list of suggestions.

    The dictionary has the following keys: name, look_text, npcs_sold*, value_sell, npcs_bought*, value_buy.
        *npcs_sold and npcs_bought are list, each element is a dictionary with the keys: name, city."""

    # Reading item database
    c = tibiaDatabase.cursor()

    # Search query
    c.execute("SELECT * FROM items WHERE title LIKE ? ORDER BY LENGTH(title) ASC LIMIT 15", ("%" + name + "%",))
    result = c.fetchall()
    if len(result) == 0:
        return None
    elif result[0]["title"].lower() == name.lower() or len(result) == 1:
        item = result[0]
    else:
        return [x['title'] for x in result]
    try:
        c.execute("SELECT npc.name, npc.city, npcs_selling.value, currency.name as currency "
                  "FROM npcs_selling "
                  "LEFT JOIN npcs npc on npc.id = npc_id "
                  "LEFT JOIN items currency on currency.id = currency "
                  "WHERE item_id = ? "
                  "ORDER BY npcs_selling.value ASC", (item["id"],))
        item["sellers"] = c.fetchall()

        c.execute("SELECT npc.name, npc.city, npcs_buying.value, currency.name as currency "
                  "FROM npcs_buying "
                  "LEFT JOIN npcs npc on npc.id = npc_id "
                  "LEFT JOIN items currency on currency.id = currency "
                  "WHERE item_id = ? "
                  "ORDER BY npcs_buying.value DESC", (item["id"],))
        item["buyers"] = c.fetchall()
        c.execute("SELECT creature.title as name, chance "
                  "FROM creatures_drops "
                  "LEFT JOIN creatures creature on creature.id = creature_id "
                  "WHERE item_id = ? "
                  "ORDER BY chance DESC ", (item["id"],))
        item["loot_from"] = c.fetchall()
        c.execute("SELECT quests.name "
                  "FROM quests_rewards "
                  "INNER JOIN quests ON quests.id = quests_rewards.quest_id "
                  "WHERE item_id = ? ", (item["id"],))
        item["quests_reward"] = c.fetchall()
        # Get item's properties:
        c.execute("SELECT * FROM items_attributes WHERE item_id = ?", (item["id"],))
        results = c.fetchall()
        item["attributes"] = {}
        for row in results:
            if row["attribute"] == "imbuement":
                temp = item["attributes"].get("imbuements", list())
                temp.append(row["value"])
                item["attributes"]["imbuements"] = temp
            else:
                item["attributes"][row["attribute"]] = row["value"]
        return item
    finally:
        c.close()


def get_rashid_info() -> Dict[str, Union[str, int]]:
    """Returns a dictionary with rashid's info

    Dictionary contains: the name of the week, city and x,y,z, positions."""
    offset = get_tibia_time_zone() - get_local_timezone()
    # Server save is at 10am, so in tibia a new day starts at that hour
    tibia_time = dt.datetime.now() + dt.timedelta(hours=offset - 10)
    c = tibiaDatabase.cursor()
    c.execute("SELECT * FROM rashid_positions WHERE day = ?", (tibia_time.weekday(),))
    info = c.fetchone()
    c.close()
    return info


def get_spell(name):
    """Returns a dictionary containing a spell's info, a list of possible matches or None"""
    c = tibiaDatabase.cursor()
    try:
        c.execute("SELECT * FROM spells WHERE words LIKE ? or name LIKE ?", (name,)*2)
        spell = c.fetchone()
        if spell is None:
            c.execute("SELECT * FROM spells WHERE words LIKE ? OR name LIKE ? ORDER BY LENGTH(name) LIMIT 15",
                      ("%" + name + "%",)*2)
            result = c.fetchall()
            if len(result) == 0:
                return None
            elif result[0]["name"].lower() == name.lower() or result[0]["words"].lower() == name.lower() or len(
                    result) == 1:
                spell = result[0]
            else:
                return ["{name} ({words})".format(**x) for x in result]
        spell["npcs"] = []
        c.execute("""SELECT npcs.title as name, npcs.city, npcs_spells.knight, npcs_spells.paladin,
                  npcs_spells.sorcerer, npcs_spells.druid FROM npcs, npcs_spells
                  WHERE npcs_spells.spell_id = ? AND npcs_spells.npc_id = npcs.id""", (spell["id"],))
        result = c.fetchall()
        for npc in result:
            npc["city"] = npc["city"].title()
            spell["npcs"].append(npc)
        return spell

    finally:
        c.close()


def get_npc(name):
    """Returns a dictionary containing a NPC's info, a list of possible matches or None"""
    c = tibiaDatabase.cursor()
    try:
        # search query
        c.execute("SELECT * FROM npcs WHERE title LIKE ? ORDER BY LENGTH(title) ASC LIMIT 15", ("%" + name + "%",))
        result = c.fetchall()
        if len(result) == 0:
            return None
        elif result[0]["title"].lower() == name.lower or len(result) == 1:
            npc = result[0]
        else:
            return [x["title"] for x in result]

        c.execute("SELECT item.title as name, npcs_selling.value, currency.name as currency "
                  "FROM npcs_selling "
                  "LEFT JOIN items item on item.id = item_id "
                  "LEFT JOIN items currency on currency.id = currency "
                  "WHERE npc_id = ? "
                  "ORDER BY npcs_selling.value DESC", (npc["id"],))
        npc["selling"] = c.fetchall()

        c.execute("SELECT item.title as name, npcs_buying.value, currency.name as currency "
                  "FROM npcs_buying "
                  "LEFT JOIN items item on item.id = item_id "
                  "LEFT JOIN items currency on currency.id = currency "
                  "WHERE npc_id = ? "
                  "ORDER BY npcs_buying.value DESC", (npc["id"],))
        npc["buying"] = c.fetchall()

        c.execute("SELECT spell.name, spell.price, npcs_spells.knight, npcs_spells.sorcerer, npcs_spells.paladin, "
                  "npcs_spells.druid "
                  "FROM npcs_spells "
                  "INNER JOIN spells spell ON spell.id = spell_id "
                  "WHERE npc_id = ? "
                  "ORDER BY price DESC", (npc["id"],))
        npc["spells"] = c.fetchall()

        c.execute("SELECT destination as name, price, notes "
                  "FROM npcs_destinations "
                  "WHERE npc_id = ? "
                  "ORDER BY name ASC", (npc["id"],))
        npc["destinations"] = c.fetchall()
        return npc
    finally:
        c.close()


def get_key(number):
    """Returns a dictionary containing a NPC's info, a list of possible matches or None"""
    c = tibiaDatabase.cursor()
    try:
        # search query
        c.execute("SELECT items_keys.*, item.image FROM items_keys "
                  "INNER JOIN items item ON item.id = items_keys.item_id "
                  "WHERE number = ? ", (number,))
        result = c.fetchone()
        return result
    finally:
        c.close()


def search_key(terms):
    """Returns a dictionary containing a NPC's info, a list of possible matches or None"""
    c = tibiaDatabase.cursor()
    try:
        # search query
        c.execute("SELECT items_keys.*, item.image FROM items_keys "
                  "INNER JOIN items item ON item.id = items_keys.item_id "
                  "WHERE items_keys.name LIKE ? OR notes LIKE ? or origin LIKE ? LIMIT 10 ", ("%" + terms + "%",)*3)
        result = c.fetchall()
        if len(result) == 0:
            return None
        elif len(result) == 1:
            return result[0]
        return result
    finally:
        c.close()


def get_achievement(name):
    """Returns an achievement (dictionary), a list of possible matches or none"""
    c = tibiaDatabase.cursor()
    try:
        # Search query
        c.execute("SELECT * FROM achievements WHERE name LIKE ? ORDER BY LENGTH(name) ASC LIMIT 15",
                  ("%" + name + "%",))
        result = c.fetchall()
        if len(result) == 0:
            return None
        elif result[0]["name"].lower() == name.lower() or len(result) == 1:
            return result[0]
        else:
            return [x['name'] for x in result]
    finally:
        c.close()


def get_mapper_link(x, y, z):
    def convert_pos(pos):
        return f"{(pos&0xFF00)>>8}.{pos&0x00FF}"
    return f"http://tibia.wikia.com/wiki/Mapper?coords={convert_pos(x)}-{convert_pos(y)}-{z}-4-1-1"
