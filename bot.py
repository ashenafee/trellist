import json
import os
from pathlib import Path

import slack
from dotenv import load_dotenv
from flask import Flask, request, Response
from slackeventsapi import SlackEventAdapter
from trello import TrelloClient

from Trello.TList import TList

env_path = Path('.') / '.env'
load_dotenv(dotenv_path=env_path)

app = Flask(__name__)
slack_event_adapter = SlackEventAdapter(os.environ['SLACK_SIGNING_SECRET'], "/slack/events", app)

client = slack.WebClient(token=os.environ['SLACK_TOKEN'])
BOT_ID = client.api_call("auth.test")["user_id"]

message_counts = {}

# TRELLO RELATED #####
load_dotenv()
TRELLO_API_KEY = os.getenv("TRELLO_API_KEY")
TRELLO_API_SECRET = os.getenv("TRELLO_API_SECRET")
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN")
TRELLO_TOKEN_SECRET = os.getenv("TRELLO_TOKEN_SECRET")

trello_client = TrelloClient(
    api_key=TRELLO_API_KEY,
    api_secret=TRELLO_API_SECRET,
    token=TRELLO_TOKEN,
    token_secret=TRELLO_TOKEN_SECRET
)

all_boards = trello_client.list_boards()
order_board = all_boards[2]
tlists = []
for i in range(len(order_board.list_lists())):
    curr = order_board.list_lists()[i]
    tlists.append(TList(curr.id, curr.name, curr.closed, curr.list_cards()))


@slack_event_adapter.on("message")
def message(payload):
    event = payload.get("event", {})
    channel_id = event.get("channel")
    user_id = event.get("user")
    text = event.get("text")

    if BOT_ID != user_id:
        if user_id in message_counts:
            message_counts[user_id] += 1
        else:
            message_counts[user_id] = 1


@app.route('/ping', methods=['POST'])
def ping():
    data = request.form
    channel_id = data.get('channel_id')
    client.chat_postMessage(channel=channel_id, text="Pong!")
    return Response(), 200


@app.route('/information', methods=['POST'])
def information():
    data = request.form
    open_lists = [tlist for tlist in tlists if not tlist.closed]
    closed_lists = [tlist for tlist in tlists if tlist.closed]

    if data.get('text') != '':
        info_str = ""
        list_names = []
        i = 1
        options = []

        if data.get('text') == 'open':
            info_str = _dropdown_options(i, info_str, list_names, open_lists, options)
            length = len(open_lists)
        else:
            info_str = _dropdown_options(i, info_str, list_names, closed_lists, options)
            length = len(closed_lists)
        info_str = info_str.strip()
        payload = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{order_board.name}'s {data.get('text')} lists",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"This Trello board has *{length}* {data.get('text')} lists:"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{info_str}"
                }
            },
            {
                "type": "input",
                "element": {
                    "type": "static_select",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Select a list",
                        "emoji": True
                    },
                    "options": options,
                    "action_id": "static_select-action"
                },
                "label": {
                    "type": "plain_text",
                    "text": "Information on...",
                    "emoji": True
                }
            }
        ]
        client.chat_postMessage(channel=data.get('channel_id'), blocks=payload)
    else:
        most_cards = max([len(tlist.cards) for tlist in open_lists])
        most_cards_name = [tlist.name for tlist in open_lists if len(tlist.cards) == most_cards][0]
        least_cards = min([len(tlist.cards) for tlist in open_lists])
        least_cards_name = [tlist.name for tlist in open_lists if len(tlist.cards) == least_cards][0]

        payload = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{order_board.name}'s Lists",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Open lists:*\n{len([tlists[i] for i in range(len(tlists)) if not tlists[i].closed])}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Closed lists:*\n{len([tlists[i] for i in range(len(tlists)) if tlists[i].closed])}"
                    }
                ]
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Most items:*\n{most_cards_name} - {most_cards}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Least items:*\n{least_cards_name} - {least_cards}"
                    }
                ]
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": f"Access {order_board.name}",
                            "emoji": True
                        },
                        "value": "access_board",
                        "action_id": "actionId-0",
                        "url": f"{order_board.url}"
                    }
                ]
            }
        ]
        client.chat_postMessage(channel=data.get('channel_id'), blocks=payload)

    return Response(), 200


def _dropdown_options(i, info_str, list_names, open_lists, options):
    for tlist in open_lists:
        list_names.append(tlist.name)
        options.append({
            "text": {
                "type": "plain_text",
                "text": tlist.name,
                "emoji": True
            },
            "value": f"value-{i}"
        })
        info_str += f"*{i}*\t_{tlist.name}_\n"
        i += 1
    return info_str


@app.route('/slack/message_action', methods=['POST'])
def list_information():
    data = json.loads(request.form['payload'])
    value_code = list(data.get('state').get('values').keys())[0]
    list_name = data.get('state') \
        .get('values') \
        .get(value_code) \
        .get('static_select-action') \
        .get('selected_option') \
        .get('text').get('text')

    # Get tlist with name
    tlist = [tlist for tlist in tlists if tlist.name == list_name][0]
    tlist_size = len(tlist.cards)
    # Send message with list information
    info = ''
    i = 1
    if not tlist.cards:
        info = f"Why not <{order_board.url}|add> some cards?"
    else:
        for card in tlist.cards:
            info += f"*{i}*\t_{card.name}_\n"
            i += 1
    payload = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{tlist.name}'s cards",
                "emoji": True
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"This Trello list has *{tlist_size}* cards:"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"{info}"
            }
        },
    ]
    print(data.get('channel'))
    client.chat_postMessage(channel=data.get('channel').get('id'), blocks=payload)

    return Response(), 200


@app.route('/create-list', methods=['POST'])
def create_list():
    data = request.form

    if data.get('text') != '':
        list_name = data.get('text')
        if type(list_name) == tuple:
            list_name = ''.join(list_name)
        order_board.add_list(list_name)
        payload = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "Success",
                        "emoji": True
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*'{list_name}'* has just been added to your board.\nCheck it out "
                                f"<{order_board.url}|here> :nerd_face:!"
                    }
                }
            ]
        client.chat_postMessage(channel=data.get('channel_id'), blocks=payload)
    else:
        client.chat_postMessage(channel=data.get('channel_id'), text="Please enter a list name")

    return Response(), 200


@app.route('/close-list', methods=['POST'])
def close_list():
    data = request.form

    if data.get('text') != '':
        list_name = data.get('text')
        if type(list_name) == tuple:
            list_name = ''.join(list_name)
        list_to_close = [list for list in order_board.list_lists() if list.name == list_name][0]
        list_to_close.close()
        payload = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "Success",
                        "emoji": True
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*'{list_name}'* has just been removed from your board.\nCheck it out "
                                f"<{order_board.url}|here> :nerd_face:!"
                    }
                }
            ]
        client.chat_postMessage(channel=data.get('channel_id'), blocks=payload)
    else:
        client.chat_postMessage(channel=data.get('channel_id'), text="Please enter a list name")

    return Response(), 200


@app.route('/add-card', methods=['POST'])
def add_card():
    data = request.form

    if data.get('text') != '':
        input_info = data.get('text')
        if '~' in input_info:
            list_name, card_name = input_info.split('~')
            tlist = [tlist for tlist in order_board.list_lists() if tlist.name == list_name][0]
            tlist.add_card(card_name)
            payload = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "Success",
                        "emoji": True
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*'{card_name}'* has just been added to *'{list_name}'* :nerd_face:"
                    }
                }
            ]
            client.chat_postMessage(channel=data.get('channel_id'), blocks=payload)
        else:
            client.chat_postMessage(channel=data.get('channel_id'), text="Please enter a list name and a card name")
    else:
        client.chat_postMessage(channel=data.get('channel_id'), text="Please enter both a list and card name")

    return Response(), 200


@app.route('/delete-card', methods=['POST'])
def delete_card():
    data = request.form

    if data.get('text') != '':
        input_info = data.get('text')
        if '~' in input_info:
            list_name, card_name = input_info.split('~')
            tlist = [tlist for tlist in order_board.list_lists() if tlist.name == list_name][0]
            card = [card for card in tlist.list_cards() if card.name == card_name][0]
            card.delete()
            payload = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "Success",
                        "emoji": True
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*'{card_name}'* has just been deleted from *'{list_name}'* :nerd_face:"
                    }
                }
            ]
            client.chat_postMessage(channel=data.get('channel_id'), blocks=payload)
        else:
            client.chat_postMessage(channel=data.get('channel_id'), text="Please enter a list name and a card name")
    else:
        client.chat_postMessage(channel=data.get('channel_id'), text="Please enter both a list and card name")

    return Response(), 200


if __name__ == '__main__':
    app.run(debug=True)
