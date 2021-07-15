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