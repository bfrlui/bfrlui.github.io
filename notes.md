[mirum testing]
https://op-ww-reg.mirumhk.com/dated/modify/WW6185cdfb75836/tc?r=WW6185cdfb75836
https://op-ww-reg.mirumhk.com/dated/modify/WWac83532120886/tc?r=WWac83532120886
https://op-ww-reg.mirumhk.com/opendated/manage/WW1886cc5f18739/tc
https://op-ww-reg.mirumhk.com/opendated/manage/WWac83532120886/tc

[mtcaptcha]
MTCaptcha: https://admin.mtcaptcha.com/login
Email : op.mhk@mirumagency.com
PW : M83Xwb2x
 
dev-adq2ud2y-wwreservation.oceanpark.com
MTPublic-l2MBtzMdK

wwreservation.oceanpark.com.hk
MTPublic-K5c0cwAEA

Private Key for UAT site:
MTPrivat-l2MBtzMdK-VQIOuOGRZwBCDRUv5qp9qJgRYk9pvJTNGB74SYBqRGKkiUBuPA

private key for PROD site:
MTPrivat-K5c0cwAEA-hbNM4qytMNdqPv31YLy8Eczm2nH5AKnwfHzJkCYRFQfkK9Rr6A

form submit field:
mtcaptcha-verifiedtoken

[outstanding items]
- captch
- cancel api

[shared docs]
https://drive.google.com/drive/folders/1ftnbRtD_Zl2gXoDCNC7zi8mccPXQ1IFK?usp=sharing

[xd]
desktop
https://xd.adobe.com/view/d378516b-8e88-4697-90c7-279ac4c8f3ef-862b/
mobile
https://xd.adobe.com/view/ffc17b94-a496-4fdc-82f3-8174730192a2-aa92/

[technical issues]
- IE support? bootstrap v4 or v5?
- fading overflow
- QR/barcode scanning

[urls]
url for step 1 - 3
https://wwreservation.oceanpark.com/{ticket type}/{language}/index.html

url for step 4
https://wwreservation.oceanpark.com/{ticket type}/{language}/confirmation.html

url for modify
https://wwreservation.oceanpark.com/{ticket type}/{language}/index.html?r={reservation number}

total pages (html files):
3 ticket types x 3 languages + (index + confirmation) = 18 pages

[layout]
1920
left=855
right=1920-855=1065

[inventory list]
- reservation x 3
- edm x 1

[component spec.]
ticket type = 750x80
button = 235x80
checkbox = 24x24; border = 4; radius = 2
list disc = 12x12; border = 4
switch = 66x40; handler = 26.67x26.67
page title = 80, black italic
body text = 14, semi bold
section title = 28, bold; section title > mb = 40
calendar month = 22, bold
calendar weekday = 12, medium
calendar day = 18, bold
input:focus label = 12, medium; v.space = 7
input text/label = 18, medium
input border = 4
input padding = 29 40
input:focus padding = 18 40
input > help text / input = 20
checkbox > label = 19
list disc > text = 25

[api spec]
Notification
request:
/api/{ticket type}/notification
response:
{
  "success": true,
  "notification": [
    "The Exclusive Offer to Hong Kong Residents from Monday to Thursday is not applicable from Friday to Sunday and all public holidays. Please ensure the admission ticket is valid on your selected visit date upon reservation.",
    "Online reservation is not required for the guests holding the tickets with designated visiting date but they must submit the Health Declaration Form at the entrance."
  ]
}

Date of visit
request:
/api/{ticket type}/timeslots/{number of guests}
response:
{
  "success": true,
  "data": [
    {
      "date": "2020-06-01",
      "available": false,
      "full": false
    },
    {
      "date": "2020-06-02",
      "available": false,
      "full": true
    }
  ]
}

Ticket verification
request:
/api/{ticket type}/verify/{ticket number}
response:
{
  "success": true,
}

Shuttle Bus Service
request:
/api/{ticket type}/shuttleBusService/{visit date}/{number of guests}
response:
{
  "success": true,
  "data": [
    {
      "time": "10:00",
      "available": true,
      "full": false
    },
    {
      "time": "14:30",
      "available": true,
      "full": true
    }
  ]
}

Submit reservation
/{ticket type}/{language}/index.html?guestNum={number of guest}&dateOfVisit={visit date}&guest1Name={guest 1 name}&guest1Ticket={guest 1 ticket number}&guest2Name={guest 2 name}&guest2Ticket={guest 2 ticket number}&guest3Name={guest 3 name}&guest3Ticket={guest 3 ticket number}&guest4Name={guest 4 name}&guest4Ticket={guest 4 ticket number}&email={email address}&confirmEmail={confirm email address}&contactNumber={contact number}&healthDeclaration=on&optin=on&shuttleBusService=on&shuttleBusTimeSlot={time}&modify=on&reservationNumber={reservation number}

where "optin", "shuttleBusService" and "modify" are optional properties that will not be existed if off
where "reservationNumber" is only existed if "modify=on"

Modify reservation
request:
/api/{ticket type}/modify/{reservation number}
response:
{
  "success": true,
  "dateOfVisit": "20/7/2021",
  "contactNumber": "12345678",
  "email": "abc@mirumagency.com",
  shuttleBusTimeSlot: "11:59",
  shuttleBusService: true,
  guest: [
    { "name": "tester #1", "ticketNumber": "1234567890123456" },
    { "name": "tester #2", "ticketNumber": "1234567890123456" }
  ]
}

Cancel reservation
request:
/api/{ticket type}/cancel/{reservation number}
response:
{
  "success": true
}
