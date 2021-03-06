import os
import sys
import json
# from datetime import datetime
import datetime
import time

import getdata 
# from misc import misc_function
import cPickle as pickle
import requests
from flask import Flask, request


app = Flask(__name__)

RSVP_msg = "Note: Some events need RSVP, please check their details"
no_event_msg = "There's no free food during this period. Please check again later."
ask_period_msg = "When are you down to have some free food?"
greeting = "Hi there! Let's cut to the chase. When are you down to have some free food?"
longer_than_usual = "Give me 5 seconds! I'm looking up the events for you"
cant_handle_request = "Sorry, I don't understand that"

@app.route('/', methods=['GET'])
def verify():
    # when the endpoint is registered as a webhook, it must echo back
    # the 'hub.challenge' value it receives in the query arguments
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.challenge"):
        if not request.args.get("hub.verify_token") == os.environ["VERIFY_TOKEN"]:
            return "Verification token mismatch", 403
        return request.args["hub.challenge"], 200

    return "Hello world", 200


@app.route('/', methods=['POST'])
def webhook():
    # endpoint for processing incoming messaging events

    data = request.get_json()
    # log(data)  # you may not want to log every incoming message in production, but it's good for testing

    if data["object"] == "page":

        for entry in data["entry"]:
            for messaging_event in entry["messaging"]:

                if messaging_event.get("message"):  # someone sent us a message

                    sender_id = messaging_event["sender"]["id"]        # the facebook ID of the person sending you the message
                    recipient_id = messaging_event["recipient"]["id"]  # the recipient's ID, which should be your page's facebook ID
                    # message_text = messaging_event["message"]["text"]  # the message's text
                    
                    message = messaging_event["message"]
                    payload = ""
                    #if user use quick reply
                    if message.get("quick_reply"):
                        payload = message["quick_reply"]["payload"]
                        #check if data is scraped for today yet, only need to check 1 file
                        today = datetime.datetime.now().date()
                        last_mod = last_modified_date("events_today.pkl").date()
                        print("last_mod:", last_mod)
                        print("today:", today)
                        if today != last_mod:#tell user to wait a bit when we scrape
                            send_message(sender_id, longer_than_usual)
                            getdata.update_events_info()
                        
                        if (payload == 'events today'):
                            #send info for events on today
                            try:
                                f_today = open( "events_today.pkl", "rb" )
                                print("read events from events_today.pkl")
                                events_today = pickle.load(f_today)
                            except EOFError:
                                events_today =  []
                            else:
                                f_today.close()
                            print("#events today:", len(events_today))
                            respond(events_today, "today", sender_id)     
                        elif (payload == 'events tomorrow'):
                            try:
                                f_tmr = open( "events_tomorrow.pkl", "rb" )
                                print("read events from events_tomorrow.pkl")
                                events_tomorrow = pickle.load(f_tmr)
                            except EOFError:
                                events_tomorrow = []
                            else:
                                f_tmr.close()
                            print("#events tmr:", len(events_tomorrow))
                            respond(events_tomorrow, "tomorrow", sender_id)
                        elif (payload == "events {} days ahead".format(getdata.days_ahead)):
                            try:
                                f_further = open("events_further_ahead.pkl", "rb" )
                                print("read events from events_further_ahead.pkl")    
                                events_further_ahead = pickle.load(f_further)
                            except EOFError:
                                events_further_ahead = []
                            else:
                                f_further.close()
                            print("#events {} days ahead".format(getdata.days_ahead), len(events_further_ahead))
                            respond(events_further_ahead, "{} days ahead".format(getdata.days_ahead), sender_id)
                    else:
                        send_message(sender_id, cant_handle_request)
                    
                    #after getting user's preference, keep asking again`
                    send_quick_reply_message(sender_id, ask_period_msg)
                    
                if messaging_event.get("delivery"):  # delivery confirmation
                    pass

                if messaging_event.get("option"):  # option confirmation
                    pass

                if messaging_event.get("postback"):  # user clicked/tapped "postback" button in earlier message         
                    #this is to reply after user tapped "Get started" button
                    payload = messaging_event['postback']['payload']
                    sender_id = messaging_event["sender"]["id"]
                    if (payload == 'first message sent'):
                        send_quick_reply_message(sender_id, greeting)                   
    return "ok", 200


def last_modified_date(filename):
    t = os.path.getmtime(filename)
    return datetime.datetime.fromtimestamp(t)

def respond(event_list, period, sender_id):
    #mark seen, then pretend to type before replying. feels more real
    sender_action(sender_id, "mark_seen")
    time.sleep(0.5)
    sender_action(sender_id, "typing_on")
    time.sleep(0.5)    
    if len(event_list):
        # send_message(sender_id, "events {} are:".format(period))
        send_event_info_carousel(sender_id, event_list) #list events in group of carousel
        # send_message(sender_id, RSVP_msg)
    else:
        send_message(sender_id, no_event_msg) 

# datetime given from data does not specify the year, need to add the correct year
def convert_to_datetime(event_time):
    given_datetime = datetime.datetime.strptime(event_time,'%A, %B %d at %I:%M %p CST')
    correct_datetime = given_datetime.replace(year=datetime.datetime.now().year)
    return correct_datetime

def getEventsCarousel(events):
    chunks = [events[x:x+10] for x in xrange(0, len(events), 10)]
    event_groups = []
    for chunk in chunks:
        event_group = []
        for event in chunk:
            event_info = {
                    "title":event[0].encode('utf-8'),
                    "subtitle":event[1].strftime("%I:%M %p, %a") + "\n" + event[2].encode('utf-8'),
                    "default_action": {
                        "type":"web_url",
                        "url":"https://anchorlink.vanderbilt.edu"+event[4],
                        "webview_height_ratio": "compact",
                    }      
                }
            event_group.append(event_info)
        event_groups.append(event_group)
    return event_groups

#send group of 10 carousel items
def send_event_info_carousel(recipient_id, event_list):
    params = {
        "access_token": os.environ["PAGE_ACCESS_TOKEN"]
    }
    headers = {
        "Content-Type": "application/json"
    }
    
    event_groups = getEventsCarousel(event_list)
    
    for event_group in event_groups:
        data = json.dumps({
            "recipient": {
                "id": recipient_id
            },
            "message": {
                "attachment":{
                    "type":"template",
                    "payload":{
                        "template_type":"generic",
                        "image_aspect_ratio":"square",
                        "elements": event_group
                    }
                }
            }
        })
        r = requests.post("https://graph.facebook.com/v2.6/me/messages", params=params, headers=headers, data=data)
    

def send_event_info(recipient_id, event):
    event_info = "{}\nTime: {}\nLocation: {}\n".format(
                    event[0].encode('utf-8'),event[1].strftime("%I:%M %p, %A"),event[2].encode('utf-8'))

    params = {
        "access_token": os.environ["PAGE_ACCESS_TOKEN"]
    }
    headers = {
        "Content-Type": "application/json"
    }
    # data = json.dumps(raw_message)
    data = json.dumps({
        "recipient": {
            "id": recipient_id
        },
        "message": {
            "attachment":{
                "type":"template",
                "payload":{
                    "template_type":"button",
                    "text":event_info,
                    "buttons":[
                        #event[4] is part of the link to event on anchorlink
                        {
                            "type":"web_url",
                            "url":"https://anchorlink.vanderbilt.edu"+event[4],
                            "title":"Details",
                            "webview_height_ratio": "compact",
                        }
                    ]
                }
            }
        }
    })
    r = requests.post("https://graph.facebook.com/v2.6/me/messages", params=params, headers=headers, data=data)



def send_quick_reply_message(recipient_id, message_text):
    params = {
        "access_token": os.environ["PAGE_ACCESS_TOKEN"]
    }
    headers = {
        "Content-Type": "application/json"
    }
    # data = json.dumps(raw_message)
    data = json.dumps({
        "recipient": {
            "id": recipient_id
        },
        "message": {
            "text":message_text,
            "quick_replies":[
                {
                    "content_type":"text",
                    "title":"Today",
                    "payload":"events today"
                },
                {
                    "content_type":"text",
                    "title":"Tomorrow",
                    "payload":"events tomorrow"
                },
                {
                    "content_type":"text",
                    "title":"{} days ahead".format(getdata.days_ahead),
                    "payload":"events {} days ahead".format(getdata.days_ahead)
                }
            ]
        }
    })
    r = requests.post("https://graph.facebook.com/v2.6/me/messages", params=params, headers=headers, data=data)

def sender_action(user_id, action):
    params = {
        "access_token": os.environ["PAGE_ACCESS_TOKEN"]
    }
    headers = {
        "Content-Type": "application/json"
    }
    data = json.dumps({
        "recipient": {
            "id": user_id
        },
        "sender_action":action
    })
    r = requests.post("https://graph.facebook.com/v2.6/me/messages", params=params, headers=headers, data=data)


def send_message(recipient_id, message_text):
    params = {
        "access_token": os.environ["PAGE_ACCESS_TOKEN"]
    }
    headers = {
        "Content-Type": "application/json"
    }
    data = json.dumps({
        "recipient": {
            "id": recipient_id
        },
        "message": {
            "text": message_text
        }
    })
    r = requests.post("https://graph.facebook.com/v2.6/me/messages", params=params, headers=headers, data=data)


def log(msg, *args, **kwargs):  # simple wrapper for logging to stdout on heroku
    try:
        if type(msg) is dict:
            msg = json.dumps(msg)
        else:
            msg = unicode(msg).format(*args, **kwargs)
        print u"{}: {}".format(datetime.datetime.now(), msg)
    except UnicodeEncodeError:
        pass  # squash logging errors in case of non-ascii text
    sys.stdout.flush()


if __name__ == '__main__':
    app.run(debug=False)
