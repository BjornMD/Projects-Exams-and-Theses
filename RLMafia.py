#RLMafia

import discord
from discord import app_commands
from discord.ext import commands
import random
import asyncio

intents = discord.Intents.default()
intents.members = True
intents.messages = True
intents.reactions = True
bot = commands.Bot(command_prefix='/', intents=intents.all())

# Global variables for queue and game state
queue_in_progress = False
max_queue_size = 8
queue_1 = []
players_voted = 0
leave_disabled = False  
voting_complete = False

@bot.event
async def on_ready():
    print(f'{bot.user.name} is now running!')
    try:
        synced = await bot.tree.sync()
        print(f'Synced {len(synced)} command(s)')
    except Exception as e:
        print(e)

def format_queue_members():
    """
    Utility function to create an embed that displays the list of queue members.
    """
    embed = discord.Embed(
        title="Current Queue",
        color=discord.Color.blue()
    )

    if not queue_1:
        embed.description = "The queue is currently empty."
    else:
        queue_mentions = "\n".join([f"{bot.get_user(player_id).mention}" for player_id in queue_1 if bot.get_user(player_id)])
        embed.description = f"Players in the queue:\n{queue_mentions}"

    return embed

@bot.tree.command(name="queue")
async def queue(interaction: discord.Interaction):
    global queue_in_progress, queue_1

    if queue_in_progress:
        if interaction.user.id not in queue_1:
            if len(queue_1) < max_queue_size:
                queue_1.append(interaction.user.id)
                await interaction.response.send_message(f"{interaction.user.mention} has joined the queue.")
                # Display updated queue members as an embed
                await interaction.followup.send(embed=format_queue_members())
            else:
                await interaction.response.send_message("The queue is full. Please wait for the next game.")
        else:
            await interaction.response.send_message("You are already in the queue.")
    else:
        queue_in_progress = True
        queue_1.append(interaction.user.id)
        await interaction.response.send_message(f"A new queue has started! {interaction.user.mention} has joined the queue.")
        # Display updated queue members as an embed
        await interaction.followup.send(embed=format_queue_members())

@bot.tree.command(name="leave")
async def leave(interaction: discord.Interaction):
    global queue_in_progress, queue_1, leave_disabled, voting_complete

    # Prevent leaving if the leave command is disabled or voting is not complete
    if leave_disabled or not voting_complete:
        await interaction.response.send_message("You cannot leave the queue right now. Please wait until the voting is complete.")
        return

    if queue_in_progress and interaction.user.id in queue_1:
        queue_1.remove(interaction.user.id)
        await interaction.response.send_message(f"{interaction.user.mention} has left the queue.")
        
        # Display updated queue members as an embed
        await interaction.followup.send(embed=format_queue_members())

        if not queue_1:  # If the queue is empty
            queue_in_progress = False  # Reset queue_in_progress flag
    else:
        await interaction.response.send_message("You are not in the queue.")

async def handle_voting_complete():
    """
    Function to be called when voting is complete.
    This will enable the /leave command again.
    """
    global voting_complete
    voting_complete = True  # Allow players to leave after voting is done
    await bot.get_channel(YOUR_CHANNEL_ID).send("Voting is complete! Players can now leave the queue if they wish.")


@bot.tree.command(name="status")
async def status(interaction: discord.Interaction):
    global queue_in_progress, queue_1

    if queue_in_progress:
        if not queue_1:
            await interaction.response.send_message("The queue is empty.")
            return

        queue_mentions = "\n".join([interaction.guild.get_member(player).mention for i, player in enumerate(queue_1)])

        embed = discord.Embed(
            title="Queue",
            description=queue_mentions,
            color=discord.Color.blue()
        )

        embed.set_footer(text=f"Total players in the queue: {len(queue_1)}")
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message("The queue is empty.")


class View(discord.ui.View):
    def __init__(self):
        super().__init__()

game_in_progress = False

@bot.tree.command(name="ready")
async def ready(interaction: discord.Interaction):
    await interaction.response.defer()  # Defer to avoid "application did not respond" issue

    global queue_in_progress, queue_1, game_in_progress, players_voted, leave_disabled

    if game_in_progress:
        await interaction.followup.send("The game is already in progress.", ephemeral=True)
        return

    if queue_in_progress:
        if len(queue_1) < 1:  # Adjusted for testing
            await interaction.followup.send("Not enough players to start the game. Minimum 1 player required for testing.", ephemeral=True)
            return

        # Initialize the team selection process
        team_selection_instance = TeamSelection()
        team_selection_instance.participants = [bot.get_user(player) for player in queue_1]  # Fetch user objects for participants

        # Generate the embed showing the current queue members
        queue_mentions = "\n".join([f"{bot.get_user(player).mention}" for player in queue_1 if bot.get_user(player) is not None])
        
        embed = discord.Embed(
            title="Queue Members",
            description=f"Players in the queue:\n{queue_mentions}",
            color=discord.Color.blue()
        )

        # Create the interactive message with buttons for team selection
        team_selection_view = TeamSelectionView(team_selection_instance)
        team_selection_instance.message = await interaction.followup.send(
            "Vote for team selection started! Choose between Random Teams or Captains.",
            embed=embed,  # Attach the embed showing queue members
            view=team_selection_view  # Attach the view with buttons
        )

        game_in_progress = True  # Set the flag to indicate game is in progress
        leave_disabled = True  # Disable the /leave command
        players_voted = 0  # Reset the players_voted count when starting a new vote

        # Set a timer to re-enable /leave after 5 minutes
        await asyncio.sleep(300)  # 5 minutes in seconds
        leave_disabled = False

    else:
        await interaction.followup.send("No queue in progress.", ephemeral=True)



class TeamSelection:
    def __init__(self):
        self.votes = {"random": 0, "captains": 0}
        self.view = None
        self.message = None
        self.voted_users = set()  # Store the voted users here

    async def handle_vote(self, option, interaction):
        global players_voted  # Access the global variable
        if option in self.votes:
            self.votes[option] += 1
            self.voted_users.add(interaction.user.id)  # Add the user to the voted_users set
            players_voted += 1  # Increment the count of players who have voted
            await self.update_view()  # Update the embed view

            # Check if all players have voted
            if players_voted == len(self.participants):
                # Determine the winning team selection method
                winning_option = self.get_voting_result()
                await handle_team_selection(interaction, winning_option)

    async def update_view(self):
        # Filter the participants to exclude users who have voted
        participants = [user for user in self.participants if user.id not in self.voted_users]

        result = self.get_voting_result()
        random_votes = self.votes["random"]
        captains_votes = self.votes["captains"]

        queue_mentions = "\n".join([f"- {user.mention}" for user in participants])

        embed = discord.Embed(
            title="Team Selection Vote",
            description=f"The current vote results are:\n"
                        f"Random Teams: {random_votes} votes\n"
                        f"Captains: {captains_votes} votes\n\n"
                        f"Yet to vote:\n{queue_mentions}",
            color=discord.Color.blurple()
        )

        await self.message.edit(embed=embed)

    def get_voting_result(self):
        random_votes = self.votes["random"]
        captains_votes = self.votes["captains"]

        if random_votes > captains_votes:
            return "random"
        elif captains_votes > random_votes:
            return "captains"
        else:
            return "random"  # In case of a tie, default to random




class TeamSelectionView(discord.ui.View):
    def __init__(self, team_selection):
        super().__init__()
        self.team_selection = team_selection
        self.add_item(TeamSelectionButton("Random Teams", "random", self.team_selection))
        self.add_item(TeamSelectionButton("Captains", "captains", self.team_selection))

class TeamSelectionButton(discord.ui.Button):
    def __init__(self, label, option, team_selection):
        super().__init__(style=discord.ButtonStyle.blurple, label=label)
        self.option = option
        self.team_selection = team_selection

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id not in self.team_selection.voted_users:
            self.team_selection.voted_users.add(interaction.user.id)
            await self.team_selection.handle_vote(self.option, interaction)
            await interaction.response.send_message(f"You voted for: {self.label}", ephemeral=True)
        else:
            await interaction.response.send_message("You have already voted.", ephemeral=True)






async def handle_team_selection(interaction: discord.Interaction, option):
    if option == "random":
        await handle_random_team_selection(interaction)
    elif option == "captains":
        await handle_captains_team_selection(interaction)


# Inside the handle_random_team_selection function
async def handle_random_team_selection(team_selection_interaction):
    global queue_1
    print('random')
    # Shuffle the queue to randomize player order
    random.shuffle(queue_1)

    # Initialize empty lists for two teams
    team_1 = []
    team_2 = []

    # Iterate over shuffled participants and alternately assign to teams
    for i, participant in enumerate(queue_1):
        if i % 2 == 0:
            team_1.append(participant)
        else:
            team_2.append(participant)

    # Create the embedded message to display teams
    embed = discord.Embed(
        title="Random Team Selection Result",
        color=discord.Color.green()
    )
    embed.add_field(name="Team 1", value="\n".join([team_selection_interaction.guild.get_member(user_id).mention for user_id in team_1]), inline=False)
    embed.add_field(name="Team 2", value="\n".join([team_selection_interaction.guild.get_member(user_id).mention for user_id in team_2]), inline=False)
    print('random')
    await send_roles_and_display_teams(team_selection_interaction.message, team_1, team_2)


async def handle_captains_team_selection(team_selection_interaction):
    global queue_1

    # Shuffle queue and select two captains randomly
    random.shuffle(queue_1)
    captain_1 = queue_1.pop(0)
    captain_2 = queue_1.pop(0)

    # Initialize teams and selection state
    team_1 = [captain_1]  # Start with captain_1
    team_2 = [captain_2]  # Start with captain_2
    remaining_players = queue_1[:]  # Copy the rest of the players for selection

    # Captains' pick pattern: [captain_1, captain_2, captain_2, captain_1, captain_2, captain_1, ...]
    pick_order = [captain_1, captain_2, captain_2, captain_1]
    pick_index = 0  # To track whose turn it is to pick

    # Send initial message to announce captains
    await team_selection_interaction.channel.send(f"{bot.get_user(captain_1).mention} and {bot.get_user(captain_2).mention} are the captains!")

    # Function to handle player selection by captains
    async def select_player(interaction: discord.Interaction):
        nonlocal pick_index, team_1, team_2, remaining_players

        # Get the current captain who is picking
        current_captain = pick_order[pick_index % len(pick_order)]

        selected_player_id = int(interaction.data['custom_id'])  # Fetch selected player ID from button

        # Add selected player to the correct team
        if current_captain == captain_1:
            team_1.append(selected_player_id)
        else:
            team_2.append(selected_player_id)

        # Remove selected player from remaining players
        remaining_players.remove(selected_player_id)

        # Update pick index
        pick_index += 1

        # Provide feedback to the channel and current captain
        await interaction.response.send_message(f"{bot.get_user(selected_player_id).mention} has been selected by {bot.get_user(current_captain).mention}.", ephemeral=True)

        # Check if selection is complete
        if not remaining_players:
            await team_selection_interaction.channel.send("All players have been selected!")
            # Display final teams here
            team_1_mentions = "\n".join([bot.get_user(user_id).mention for user_id in team_1])
            team_2_mentions = "\n".join([bot.get_user(user_id).mention for user_id in team_2])

            embed = discord.Embed(
                title="Team Selection Result",
                description=f"**Team 1**:\n{team_1_mentions}\n\n**Team 2**:\n{team_2_mentions}",
                color=discord.Color.green()
            )
            await team_selection_interaction.channel.send(embed=embed)
            return

        # Prepare next captain's turn
        next_captain = pick_order[pick_index % len(pick_order)]
        # Create a new set of buttons for the remaining players
        view = discord.ui.View()
        for player_id in remaining_players:
            view.add_item(discord.ui.Button(label=f"Select {bot.get_user(player_id).name}", custom_id=str(player_id), style=discord.ButtonStyle.primary))

        # Notify the next captain to select a player
        await bot.get_user(next_captain).send(f"Select a player for your team:", view=view)

    # Start the selection with the first captain (captain_1)
    view = discord.ui.View()
    for player_id in remaining_players:
        view.add_item(discord.ui.Button(label=f"Select {bot.get_user(player_id).name}", custom_id=str(player_id), style=discord.ButtonStyle.primary))

    await bot.get_user(captain_1).send(f"Select a player for your team:", view=view)




async def send_roles_and_display_teams(message, team_1, team_2):
    total_players = len(team_1) + len(team_2)

    if total_players <= 5:
        mafia_count = 1
        villager_count = total_players - mafia_count
        roles = ["Mafia"] * mafia_count + ["Villager"] * villager_count
    else:
        mafia_count_per_team = 1
        villager_count_per_team = len(team_1) + len(team_2) - (2 * mafia_count_per_team)
        roles = ["Mafia"] * mafia_count_per_team + ["Villager"] * villager_count_per_team

    random.shuffle(roles)
    team_roles = {}

    for user_id in team_1 + team_2:
        user = message.guild.get_member(user_id)
        role = roles.pop()
        team_roles[user_id] = role
        await user.send(f"You are a {role}!")

    team_1_mentions = [message.guild.get_member(user_id).mention for user_id in team_1]
    team_2_mentions = [message.guild.get_member(user_id).mention for user_id in team_2]

    team_1_text = "\n".join(team_1_mentions)
    team_2_text = "\n".join(team_2_mentions)

    embed = discord.Embed(
        title="Team Selection Result",
        description=f"**Team 1**:\n{team_1_text}\n\n**Team 2**:\n{team_2_text}",
        color=discord.Color.green()
    )

    await message.channel.send(embed=embed)


bot.run('MTA4ODgyMzcyNDM2ODczMjE4MA.G0HBAX.Hk7Y_HE56HPZz_WK0J8JIxi1dWNzn0egzaSEY8')