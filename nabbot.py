from utils import *
from config import *
from tibia import *

description = '''Mission: Destroy all humans.'''
bot = commands.Bot(command_prefix=["/"], description=description, pm_help=True)

@bot.event
@asyncio.coroutine
def on_ready():
    bot.load_extension("tibia")
    print('Logged in as')
    print(bot.user.name)
    print(bot.user.id)
    print('------')
    log.info('Bot is online and ready')
    #expose bot to ultis.py
    ##its either this or importing discord and commands in utils.py...
    utilsGetBot(bot)
    #Notify reset author
    if len(sys.argv) > 1:
        user = getUserById(sys.argv[1])
        if user is not None:
            yield from bot.send_message(user,"Restart complete")
    #start up think()
    yield from think()
    #######################################
    ###anything below this is dead code!###
    #######################################


@bot.event
@asyncio.coroutine
def on_command(command, ctx):
    if ctx.message.channel.is_private:
        destination = 'PM'
    else:
        destination = '#{0.channel.name} ({0.server.name})'.format(ctx.message)

    log.info('Command by {0.author.name} in {1}: {0.content}'.format(ctx.message, destination))

@bot.event
@asyncio.coroutine
def on_member_join(member):
    message = "Welcome {0.mention}! Please tell us about yourself, who is your Tibia character?\r\nSay /im *charactername* and I'll begin tracking it for you!"
    log.info("New member joined: {0.name} (ID: {0.id})".format(member))
    ##Starting a private message with new members allows us to keep track of them even after they leave our visible servers.
    yield from bot.start_private_message(member)
    yield from bot.send_message(member.server,message.format(member))

@bot.event
@asyncio.coroutine
def on_message_delete(message):
    log.info("{0.author.name} has deleted the message: '{0.content}'".format(message))
    for attachment in message.attachments:
        log.info(attachment)

@bot.event
@asyncio.coroutine
def on_message_edit(older_message,message):
    log.info("{0.author.name} has edited the message: '{0.content}'".format(older_message))
    for attachment in older_message.attachments:
        log.info(attachment)
    log.info("New message: '{0.content}'".format(message))
    for attachment in message.attachments:
        log.info(attachment)

########a think function!
@asyncio.coroutine
def think():
    #i could do something like, check if the bot's alive instead of just a "while true" but i dont see the point.
    lastServerOnlineCheck = datetime.now()
    lastPlayerDeathCheck = datetime.now()
    global globalOnlineList
    while 1:
        #periodically check server online lists
        if datetime.now() - lastServerOnlineCheck > serveronline_delay and len(tibiaservers) > 0:
            ##pop last server in qeue, reinsert it at the beggining
            currentServer = tibiaservers.pop()
            tibiaservers.insert(0, currentServer)

            #get online list for this server
            currentServerOnline = yield from getServerOnline(currentServer)

            if len(currentServerOnline) > 0:
                #open connection to users.db
                c = userDatabase.cursor()

                ##remove chars that are no longer online from the globalOnlineList
                offlineList = []
                for char in globalOnlineList:
                    if char.split("_",1)[0] == currentServer:
                        offline = True
                        for serverChar in currentServerOnline:
                            if serverChar['name'] == char.split("_",1)[1]:
                                offline = False
                                break
                        if offline:
                            offlineList.append(char)
                for nowOfflineChar in offlineList:
                    globalOnlineList.remove(nowOfflineChar)

                #add new online chars and announce level differences
                for serverChar in currentServerOnline:
                    c.execute("SELECT name, last_level, id FROM chars WHERE name LIKE ?",(serverChar['name'],))
                    result = c.fetchone()
                    if result:
                        #if its a stalked character
                        lastLevel = result[1]
                        if not (currentServer+"_"+serverChar['name']) in globalOnlineList:
                            ##if the character wasnt in the globalOnlineList we add them
                            #(we insert them at the beggining of the list to avoid messing with the death checks order)
                            globalOnlineList.insert(0,(currentServer+"_"+serverChar['name']))
                            ##since this is the first time we see them online we flag their last death time
                            #to avoid backlogged death announces
                            c.execute("UPDATE chars SET last_death_time = ? WHERE name LIKE ?",(None,serverChar['name'],))

                        ##else we check for levelup
                        elif lastLevel < serverChar['level'] and lastLevel > 0:
                            ##announce the level up
                            log.info("Announcing level up: "+serverChar['name'])
                            #Saving level up date in database
                            c.execute("INSERT INTO char_levelups (char_id,level,date) VALUES(?,?,?)",(result[2],serverChar['level'],time.time(),))
                            yield from announceLevel(serverChar['name'],serverChar['level'])
                        #finally we update their last level in the db
                        c.execute("UPDATE chars SET last_level = ? WHERE name LIKE ?",(serverChar['level'],serverChar['name'],))

                #Close cursor and commit changes
                userDatabase.commit()
                c.close()

            #update last server check time
            lastServerOnlineCheck = datetime.now()

        #periodically check for deaths
        if datetime.now() - lastPlayerDeathCheck > playerdeath_delay and len(globalOnlineList) > 0:
            ##pop last char in qeue, reinsert it at the beggining
            currentChar = globalOnlineList.pop()
            globalOnlineList.insert(0, currentChar)

            #get rid of server name
            currentChar = currentChar.split("_",1)[1]
            #get death list for this char
            #we only need the last death
            currentCharDeaths = yield from getPlayerDeaths(currentChar,True)

            if (type(currentCharDeaths) is list) and len(currentCharDeaths) > 0:
                c = userDatabase.cursor()

                c.execute("SELECT name, last_death_time FROM chars WHERE name LIKE ?",(currentChar,))
                result = c.fetchone()
                if result:
                    lastDeath = currentCharDeaths[0]
                    dbLastDeathTime = result[1]
                    ##if the db lastDeathTime is None it means this is the first time we're seeing them online
                    #so we just update it without announcing deaths
                    if dbLastDeathTime is None:
                        c.execute("UPDATE chars SET last_death_time = ? WHERE name LIKE ?",(lastDeath['time'],currentChar,))
                    #else if the last death's time doesn't match the one in the db
                    elif dbLastDeathTime != lastDeath['time']:
                        #update the lastDeathTime for this char in the db
                        c.execute("UPDATE chars SET last_death_time = ? WHERE name LIKE ?",(lastDeath['time'],currentChar,))
                        #and announce the death
                        log.info("Announcing death: "+currentChar)
                        yield from announceDeath(currentChar,lastDeath['time'],lastDeath['level'],lastDeath['killer'],lastDeath['byPlayer'])

                #Close cursor and commit changes
                userDatabase.commit()
                c.close()
            #update last death check time
            lastPlayerDeathCheck = datetime.now()

        #sleep for a bit and then loop back
        yield from asyncio.sleep(1)
########

########announceDeath
@asyncio.coroutine
def announceDeath(charName,deathTime,deathLevel,deathKiller,deathByPlayer):
    if int(deathLevel) < announceTreshold:
        #Don't announce for low level players
        return

    char = yield from getPlayer(charName)
    #Failsafe in case getPlayer fails to retrieve player data
    if type(char) is not dict:
        log.warning("Error in announceDeath, failed to getPlayer("+charName+")")
        return

    if not(char['world'] in tibiaservers):
        #Don't announce for players in non-tracked worlds
        return
    #Choose correct pronouns
    pronoun = ["he","his"] if char['gender'] == "male" else ["she","her"]

    channel = getChannelByServerAndName(mainserver,mainchannel)
    #Find killer article (a/an)
    deathKillerArticle = ""
    if not deathByPlayer:
        deathKillerArticle = deathKiller.split(" ",1)
        if deathKillerArticle[0] in ["a","an"] and len(deathKillerArticle) > 1:
            deathKiller = deathKillerArticle[1]
            deathKillerArticle = deathKillerArticle[0]+" "
        else:
            deathKillerArticle = ""
    #Select a message
    message = weighedChoice(deathmessages_player) if deathByPlayer else weighedChoice(deathmessages_monster)
    #Format message with player data
    message = message.format(charName,deathTime,deathLevel,deathKiller,deathKillerArticle,pronoun[0],pronoun[1])
    #Format extra stylization
    message = formatMessage(message)

    yield from bot.send_message(channel,message[:1].upper()+message[1:])
########

########announceLevel
@asyncio.coroutine
def announceLevel(charName,newLevel):
    if int(newLevel) < announceTreshold:
        #Don't announce for low level players
        return

    char = yield from getPlayer(charName)
    #Failsafe in case getPlayer fails to retrieve player data
    if type(char) is not dict:
        log.error("Error in announceLevel, failed to getPlayer("+charName+")")
        return
    #Choose correct pronouns
    pronoun = ["he","his"] if char['gender'] == "male" else ["she","her"]

    channel = getChannelByServerAndName(mainserver,mainchannel)

    #Select a message
    message = weighedChoice(levelmessages,char['vocation'],int(newLevel))
    #Format message with player data
    message = message.format(charName,newLevel,pronoun[0],pronoun[1])
    #Format extra stylization
    message = formatMessage(message)

    yield from bot.send_message(channel,message)
########

###### Bot commands
@bot.command()
@asyncio.coroutine
def roll(dice : str):
    """Rolls a dice in TdN format.

    Rolls a N-sides dice T times.
    Example:
    /roll 3d6 - Rolls a 6 sided dice 3 times"""
    try:
        rolls, limit = map(int, dice.split('d'))
    except Exception:
        yield from bot.say('Format has to be in NdN!')
        return

    result = ', '.join(str(random.randint(1, limit)) for r in range(rolls))
    yield from bot.say(result)

@bot.command(description='For when you wanna settle the score some other way')
@asyncio.coroutine
def choose(*choices : str):
    """Chooses between multiple choices."""
    yield from bot.say(random.choice(choices))

@bot.command(pass_context=True)
@asyncio.coroutine
def im(ctx,*charname : str):
    """Lets you add your first tibia character(s) for the bot to track.

    If you need to add any more characters or made a mistake, please message an admin."""
    
    ##This is equivalent to someone using /stalk addacc on themselves.
    #To avoid abuse it will only work on users who have joined recently and have no characters added to their account.

    #This command can't work on private messages, since we need a member instead of an user to be able to check the joining date.
    if ctx.message.channel.is_private:
        return

    charname = " ".join(charname).strip()
    user = ctx.message.author
    try:
        c = userDatabase.cursor()
        admins_message = " or ".join("**"+getUserById(admin).mention+"**" for admin in admin_ids)
        servers_message = ", ".join(["**"+server+"**" for server in tibiaservers])
        notallowed_message = ("I'm sorry, {0.mention}, this command is reserved for new users, if you need any help adding characters to your account please message "+admins_message+".").format(user)
        
        ##Check if the user has joined recently
        if datetime.now() - user.joined_at > timewindow_im_joining:
            yield from bot.say(notallowed_message)
            return
        ##Check that this user doesn't exist or has no chars added to it yet.
        c.execute("SELECT id from discord_users WHERE id = ?",(user.id,))
        result = c.fetchone()
        if(result is not None):
            c.execute("SELECT name,user_id FROM chars WHERE user_id LIKE ?",(user.id,))
            result = c.fetchone();
            if(result is not None):
                yield from bot.say(notallowed_message)
                return
        else:
            #Add the user if it doesn't exist
            c.execute("INSERT INTO discord_users(id) VALUES (?)",(user.id,))
        
        char = yield from getPlayer(charname)
        if(type(char) is not dict):
            if char == ERROR_NETWORK:
                yield from bot.say("I couldn't fetch the character, please try again.")
            elif char == ERROR_DOESNTEXIST:
                yield from bot.say("That character doesn't exists.")
            return
        chars = char['chars']
        #If the char is hidden,we still add the searched character
        if(len(chars) == 0):
            chars = [char]
            print(char['world'])
        skipped = []
        updated = []
        added = []
        for char in chars:
            if(char['world'] not in tibiaservers):
                skipped.append(char)
                continue
            c.execute("SELECT name,user_id FROM chars WHERE name LIKE ?",(char['name'],))
            result = c.fetchone();
            if(result is not None):
                if getUserById(result[1]) is None:
                    updated.append({'name' : char['name'], 'world' : char['world'], 'prevowner' : result[1]})
                    continue
                else:
                    yield from bot.say("I'm sorry but a character in that account was already claimed by **@{0}**.".format(getUserById(result[1]).name)+"\r\n"+
                        "Have you made a mistake? Message "+admins_message+" if you need any help!")
                    return
            char = yield from getPlayer(char['name'])
            added.append(char)
        if len(skipped) == len(chars):
            yield from bot.say("I'm sorry, I couldn't find any characters in that account from the worlds I track ("+servers_message+")\r\n"+
                        "Have you made a mistake? Message "+admins_message+" if you need any help!")
            return
        for char in updated:
            c.execute("UPDATE chars SET user_id = ? WHERE name LIKE ?",(user.id,char['name']))
            log.info("Character {0} was reasigned to {1.name} (ID: {1.id}) from /im. (Previous owner (ID: {2}) was not found)".format(char['name'],user,char['prevowner']))
        for char in added:
            c.execute("INSERT INTO chars (name,last_level,vocation,user_id) VALUES (?,?,?,?)",(char['name'],char['level']*-1,char['vocation'],user.id))
            log.info("Character {0} was asigned to {1.name} (ID: {1.id}) from /im.".format(char['name'],user))

        yield from bot.say(("Thanks {0.mention}! I have added the following character(s) to your account: "+", ".join("**"+char['name']+"**" for char in added)+", ".join("**"+char['name']+"**" for char in updated)+".\r\nFrom now on I will track level advances and deaths for you, if you need to add any more characters please message "+admins_message+".").format(user))
        return
    finally:
        c.close()
        userDatabase.commit()


@bot.command(pass_context=True)
@asyncio.coroutine
def online(ctx):
    """Tells you which users are online on Tibia

    This list gets updated based on Tibia.com online list, so it takes a couple minutes
    to be updated."""
    discordOnlineChars = []
    c = userDatabase.cursor()
    try:
        for char in globalOnlineList:
            char = char.split("_",1)[1]
            c.execute("SELECT name, user_id, vocation, last_level FROM chars WHERE name LIKE ?",(char,))
            result = c.fetchone()
            if result:
                #this will always be true unless a char is removed from chars inbetween globalOnlineList updates
                discordOnlineChars.append({"name" : result[0], "id" : result[1], "vocation" : result[2], "level" : result[3]})
        if len(discordOnlineChars) == 0:
            yield from bot.say("There is no one online from Discord.")
        else:
            reply = "The following discord users are online:"
            for char in discordOnlineChars:
                user = getUserById(char['id'])

                char['vocation'] = vocAbb(char['vocation'])
                discordName = user.name if (user is not None) else "unknown"
                reply += "\n\t{0} (Lvl {1} {2}, **@{3}**)".format(char['name'],abs(char['level']),char['vocation'],discordName)
            yield from bot.say(reply)
    finally:
        c.close()
##### Admin only commands ####

######## Makesay command
@bot.command(pass_context=True,hidden=True)
@asyncio.coroutine
def makesay(ctx,*args: str):
    if not (ctx.message.channel.is_private and ctx.message.author.id in admin_ids):
        return
    channel = getChannelByServerAndName(mainserver,mainchannel)
    yield from bot.send_message(channel," ".join(args))

@bot.command(pass_context=True,hidden=True)
@asyncio.coroutine
def stalk(ctx, subcommand, *args : str):
    if not (ctx.message.channel.is_private and ctx.message.author.id in admin_ids):
        return
    params = (" ".join(args)).split(",")
    try:
        c = userDatabase.cursor()
        ###Add user
        if(subcommand == "add"):
            if len(params) != 1:
                yield from bot.say("The correct syntax is: /stalk add username")
                return
            user = getUserByName(params[0])
            if(user is None):
                yield from bot.say("I don't see any user named **{0}**".format(params[0]))
                return
            c.execute("SELECT id from discord_users WHERE id LIKE ?",(user.id,))
            if(c.fetchone() is not None):
                yield from bot.say("**@{0}** is already registered.".format(user.name))
                return
            c.execute("INSERT INTO discord_users(id) VALUES (?)",(user.id,))
            yield from bot.say("**@{0}** was registered succesfully.".format(user.name))

        ###Add char & Add account common operations
        if(subcommand == "addchar" or subcommand == "addacc"):
            if len(params) != 2:
               yield from bot.say("The correct syntax is: /stalk {0} username,character".format(subcommand))
               return
            user = getUserByName(params[0])
            char = yield from getPlayer(params[1])
            if(user is None):
                yield from bot.say("I don't see any user named **{0}**".format(params[0]))
                return
            if(type(char) is not dict):
                if char == ERROR_NETWORK:
                    yield from bot.say("I couldn't fetch the character, please try again.")
                elif char == ERROR_DOESNTEXIST:
                    yield from bot.say("That character doesn't exists.")
                return
            ###Add char
            if(subcommand == "addchar"):
                c.execute("SELECT name,user_id FROM chars WHERE name LIKE ?",(char['name'],))
                result = c.fetchone();
                if(result is not None):
                    if(char['name'] != params[1]):
                        c.execute("UPDATE chars SET name = ? WHERE id LIKE ?",(user['name'],result[1],))
                        yield from bot.say("This character's name was changed from **{0}** to **{1}**".format(params[1],char['name']))
                    #Registered to a different user
                    if(result[1] != user.id):
                        username = "unknown" if getUserById(result[1]) is None else getUserById(result[1]).name
                        yield from bot.say("This character is already registered to **@{0}**".format(username))
                        return
                    #Registered to current user
                    yield from bot.say("This character is already registered to this user.")
                    return
                c.execute("INSERT INTO chars (name,last_level,vocation,user_id) VALUES (?,?,?,?)",(char['name'],char['level']*-1,char['vocation'],user.id))
                c.execute("SELECT id from discord_users WHERE id = ?",(user.id,))
                result = c.fetchone()
                if(result is None):
                    c.execute("INSERT INTO discord_users(id) VALUES (?)",(user.id,))
                    yield from bot.say("**@{0}** was registered succesfully.".format(user.name))
                yield from bot.say("**{0}** was registered succesfully to this user.".format(char['name']))
                return
            ###Add account
            if(subcommand == "addacc"):
                chars = char['chars']
                #If the char is hidden,we still add the searched character
                if(len(chars) == 0):
                    yield from bot.say("Character is hidden.")
                    chars = [char]
                for char in chars:
                    if(char['world'] not in tibiaservers):
                        yield from bot.say("**{0}** skipped, character not in server list.".format(char['name']))
                        continue
                    char = yield from getPlayer(char['name'])
                    c.execute("SELECT name,user_id FROM chars WHERE name LIKE ?",(char['name'],))
                    result = c.fetchone();
                    if(result is not None):
                        if(result[1] != user.id):
                            username = "unknown" if getUserById(result[1]) is None else getUserById(result[1]).name
                            yield from bot.say("**{0}** is already registered to **@{1}**".format(char['name'],username))
                            continue
                        yield from bot.say("**{0}** is already registered to this user.".format(char['name']))
                        continue
                    c.execute("INSERT INTO chars (name,last_level,vocation,user_id) VALUES (?,?,?,?)",(char['name'],char['level']*-1,char['vocation'],user.id))
                    yield from bot.say("**{0}** was registered succesfully to this user.".format(char['name']))
                c.execute("SELECT id from discord_users WHERE id = ?",(user.id,))
                result = c.fetchone()
                if(result is None):
                    c.execute("INSERT INTO discord_users(id) VALUES (?)",(user.id,))
                    yield from bot.say("**@{0}** was registered succesfully.".format(user.name))
                    return

        ###Remove char
        if(subcommand == "removechar"):
            if len(params) != 1:
                yield from bot.say("The correct syntax is: /stalk {0} character".format(subcommand))
                return
            char = params[0]
            #This could be used to remove deleted chars so we don't need to check anything
            #Except if the char exists...
            c.execute("SELECT name, user_id FROM chars WHERE name LIKE ?",(char,))
            result = c.fetchone()
            if(result is None):
                yield from bot.say("There's no character with that name registered.")
                return
            username = "unknown" if getUserById(result[1]) is None else getUserById(result[1]).name
            c.execute("DELETE FROM chars WHERE name LIKE ?",(result[0],))
            yield from bot.say("**{0}** was removed succesfully from **@{1}**.".format(result[0],username))
            return
        ###Remove user
        if(subcommand == "remove"):
            if len(params) != 1:
                yield from bot.say("The correct syntax is: /stalk {0} user".format(subcommand))
                return
            user = getUserByName(params[0])
            if(user is None):
                yield from bot.say("I don't see any user named **{0}**\nI recommend using purge to remove former users.".format(params[0]))
                return
            c.execute("SELECT id from discord_users WHERE id = ?",(user.id,))
            if(c.fetchone() is None):
                yield from bot.say("**@{0}** wasn't registered.".format(user.name))
                return
            c.execute("DELETE FROM discord_users WHERE id = ?",(user.id,))
            yield from bot.say("**@{0}** was removed succesfully.".format(user.name))
            c.execute("SELECT name FROM chars WHERE user_id = ?",(user.id,))
            result = c.fetchall()
            if len(result) >= 1:
                chars = ["**"+i[0]+"**" for i in result]
                reply = "The following chars were registered to that user, remove them or use purge to clean up:\n\t"
                reply += "\n\t".join(chars)
                yield from bot.say(reply)
            return
        ###Purge
        if(subcommand == "purge"):
            c.execute("SELECT id FROM discord_users")
            result = c.fetchall()
            if result is None:
                yield from bot.say("There are no users registered.")
                return
            delete_users = list()
            yield from bot.say("Initiating purge...")
            #Deleting users no longer in server
            for row in result:
                user = getUserById(row[0])
                if(user is None):
                    delete_users.append((row[0],))
            if len(delete_users) > 0:
                c.executemany("DELETE FROM discord_users WHERE id = ?",delete_users)
                yield from bot.say("{0} user(s) no longer in the server were removed.".format(c.rowcount))
            #Deleting chars with non-existant user
            c.execute("SELECT name FROM chars WHERE user_id NOT IN (SELECT id FROM discord_users)")
            result = c.fetchall()
            if len(result) >= 1:
                chars = ["**"+i[0]+"**" for i in result]
                reply = "{0} char(s) were assigned to a non-existant user and were deleted:\n\t".format(len(result))
                reply += "\n\t".join(chars)
                yield from bot.say(reply)
                c.execute("DELETE FROM chars WHERE user_id NOT IN (SELECT id FROM discord_users)")
            #Removing deleted chars
            c.execute("SELECT name,last_level,vocation FROM chars")
            result = c.fetchall()
            if(result is None):
                return
            delete_chars = list()
            rename_chars = list()
            #revoc_chars = list()
            for name,last_level,vocation in result:
                char = yield from getPlayer(name)
                if char == ERROR_NETWORK:
                    yield from bot.say("Couldn't fetch **{0}**, skipping...".format(name))
                    continue
                #Char was deleted
                if char == ERROR_DOESNTEXIST:
                    delete_chars.append((name,))
                    yield from bot.say("**{0}** doesn't exists, deleting...".format(name))
                    continue
                #Char was renamed
                if char['name'] != name:
                    rename_chars.append((char['name'],name,))
                    yield from bot.say("**{0}** was renamed to **{1}**, updating...".format(name,char['name']))
                ##Char vocation changed
                #if char['vocation'] != vocation:
                #    revoc_chars.append((char['vocation'],name,))
                #    yield from bot.say("**{0}**'s vocation was set to **{1}** from **{2}**, updating...".format(name,char['vocation'],vocation))
            #No need to check if user exists cause those were removed already
            if len(delete_chars) > 0:
                c.executemany("DELETE FROM chars WHERE name LIKE ?",delete_chars)
                yield from bot.say("{0} char(s) were removed.".format(c.rowcount))
            #if len(revoc_chars) > 0:
            #    c.executemany("UPDATE chars SET vocation = ? WHERE name LIKE ?",revoc_chars)
            #    yield from bot.say("{0} char(s)' vocations were updated.".format(c.rowcount))
            if len(rename_chars) > 0:
                c.executemany("UPDATE chars SET name = ? WHERE name LIKE ?",rename_chars)
                yield from bot.say("{0} char(s) were renamed.".format(c.rowcount))
            #Remove users with no chars
            c.execute("SELECT id FROM discord_users WHERE id NOT IN (SELECT user_id FROM chars)")
            result = c.fetchall()
            if len(result) >= 1:
                c.execute("DELETE FROM discord_users WHERE id NOT IN (SELECT user_id FROM chars)")
                yield from bot.say("{0} user(s) with no characters were removed.".format(c.rowcount))
            c.execute("DELETE FROM char_levelups WHERE char_id NOT IN (SELECT id FROM chars)")
            if c.rowcount > 0:
                yield from bot.say("{0} level up registries from removed characters were deleted.".format(c.rowcount))
            yield from bot.say("Purge done.")
            return
    finally:
        c.close()
        userDatabase.commit()

@stalk.error
@asyncio.coroutine
def stalk_error(error,ctx):
    if type(error) is commands.MissingRequiredArgument:
        yield from bot.say("""```Valid subcommands are:
        /stalk add user
        /stalk addchar user,char
        /stalk addacc user,char
        /stalk remove user
        /stalk removechar char
        /stalk purge```""")


######## Restart command
@bot.command(pass_context=True,hidden=True)
@asyncio.coroutine
def restart(ctx):
    if not (ctx.message.channel.is_private and ctx.message.author.id in admin_ids):
        return
    yield from bot.say('Restarting...')
    bot.logout()
    log.warning("Closing NabBot")
    if(platform.system() == "Linux"):
        os.system("python3 restart.py {0}".format(ctx.message.author.id))
    else:
        os.system("python restart.py {0}".format(ctx.message.author.id))

    quit()
########

######## Shutdown command
@bot.command(pass_context=True,hidden=True)
@asyncio.coroutine
def shutdown(ctx):
    if not (ctx.message.channel.is_private and ctx.message.author.id in admin_ids):
        return
    yield from bot.say('Shutdown...')
    bot.logout()
    log.warning("Closing NabBot")
    quit()
########


if __name__ == "__main__":
    initDatabase()
    
    login = getLogin()
    try:
        token = login.token
    except NameError:
        token = ""

    try:
        email = login.email
        password = login.password
    except NameError:
        email = ""
        password = ""
    try:
        if(token):
            bot.run(token)
        elif(email and password):
            bot.run(login.email,login.password)
        else:
            print("No login data found. Edit or delete login.py and restart.")
            input("\nPress any key to continue...")
            quit()
    except discord.errors.LoginFailure:
        print("Incorrect login data. Edit or delete login.py and restart.")
        input("\nPress any key to continue...")
        quit()
    finally:
        bot.session.close()


    log.warning("Emergency restart!")
    if(platform.system() == "Linux"):
        os.system("python3 restart.py")
    else:
        os.system("python restart.py")
    quit()
