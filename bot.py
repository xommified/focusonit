import asyncio
import os
import re
import time
import json
import logging
import sys
from datetime import datetime

import discord
from discord.ext import tasks, commands
import humanize
import requests


logger = logging.getLogger()
logger.setLevel(logging.INFO)

handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

api_url = "https://www.indiegogo.com/private_api/campaigns/2598099/pledges?page="

client = discord.Client()

username_regex = r"!focus\s+(.*)"


@tasks.loop(hours=1)
async def get_backers():
    logger.info("Reading number of pages...")
    r = requests.get(f"{api_url}1")
    if r.status_code != requests.codes.ok:
        logger.error(f"Error reading from IGG API: {r.status_code}")
        return

    page = 1
    pages = r.json()["pagination"]["pages"]
    backers = []
    while page <= pages:
        logger.info(f"Retrieving page {page} of {pages}, {page/pages*100.0:.0f}% completed.")
        r = requests.get(f"{api_url}{page}")
        while r.status_code == 429:
            logger.warning(f"Rate limit exceeded, backing off 10 seconds...")
            await asyncio.sleep(10)
            r = requests.get(f"{api_url}{page}")

        if r.status_code != requests.codes.ok:
            logger.error(f"Error reading from IGG API: {r.status_code}")
            return

        backers += r.json()["response"]
        await asyncio.sleep(0.5)

        page += 1

    backers.reverse()
    for i, backer in enumerate(backers):
        backer["place_in_line"] = i+1

    with open("backers.json", "w") as f:
        json.dump(backers, f, indent=4)


@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    game = discord.Game("!focus backer name")
    await client.change_presence(activity=game)
    get_backers.start()


@client.event
async def on_message(message):
    if message.author.bot:
        return

    if message.content.startswith('!focus'):
        try:
            username = re.search(username_regex, message.content).group(1)
        except AttributeError:
            embed = discord.Embed(
                description="Please use `!focus backer name` to invoke the bot. Name must be exact."
            )
            embed.title = "Invalid Format"
            await message.channel.send(embed=embed)
            return

        try:
            with open("backers.json") as f:
                backers = json.load(f)
                update_time = os.path.getmtime("backers.json")
                ts = datetime.utcfromtimestamp(os.path.getmtime("backers.json"))
        except FileNotFoundError:
            embed = discord.Embed(
                description="Backer list has not been dumped yet, this bot will dump backer info every hour."
            )
            embed.title = "Please focus on it."
            await message.channel.send(embed=embed)
            return

        try:
            backer_info = next(backer for backer in backers if backer["pledger_display_name"] == username)
        except StopIteration:
            embed = discord.Embed(
                description=("No such user found in backer info.\n\n"
                             "Check exact spelling, or you may have backed anonymously. "
                             "See image for how to change your profile name and set contribution visibility.\n\n"
                             "This bot will dump backer info every hour.")
            )
            embed.title = username
            embed.set_image(url="https://i.imgur.com/OoqwIds.png")
        else:
            embed = discord.Embed(
                description="""Your place in line does not guarantee delivery in that order, 
                this is for curiosity's sake only. GPD will likely ship by region."""
            )
            embed.title = backer_info["pledger_display_name"]
            embed.set_thumbnail(url=backer_info["pledger_image_url"])
            embed.add_field(name="Current place in line:", value=backer_info["place_in_line"])
            embed.add_field(name="Contribution made:", value=backer_info["time_ago"])
        finally:
            embed.set_footer(text=f"Backer info last dumped {humanize.naturaltime(datetime.now() - ts)}.")
            await message.channel.send(embed=embed)

with open("token.txt") as f:
    token = f.read()

client.run(token)
