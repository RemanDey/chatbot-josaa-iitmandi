from twilio.rest import Client

account_sid = 'AC58d82704cb2ac317880fabb771532264'
auth_token = '296fea1339c31442173f99a0bb2433ae'
client = Client(account_sid, auth_token)

message = client.messages.create(
  from_='whatsapp:+14155238886',
  body='Hehesdfgs;ge;gh',
  to='whatsapp:+919830088615'
)

print(message.sid)