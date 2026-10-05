"""Generate app icons and a clearly synthetic report for integration testing."""
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parent.parent
for size,name in [(192,"icon-192.png"),(512,"icon-512.png"),(180,"apple-touch-icon.png")]:
    image=Image.new("RGB",(size,size),"#174bc4")
    draw=ImageDraw.Draw(image)
    scale=size/192
    polygon=[(int(x*scale),int(y*scale)) for x,y in [(46,68),(63,51),(79,51),(96,70),(113,51),(130,51),(147,68),(147,88),(96,145),(46,88)]]
    draw.line(polygon+[polygon[0]],fill="white",width=max(3,int(10*scale)),joint="curve")
    image.save(ROOT/"static"/name)

def font(size):
    for name in ["/System/Library/Fonts/Supplemental/Arial.ttf","DejaVuSans.ttf"]:
        try:return ImageFont.truetype(name,size)
        except OSError:pass
    return ImageFont.load_default(size=size)

image=Image.new("RGB",(1500,1050),"white");draw=ImageDraw.Draw(image)
draw.text((65,55),"SYNTHETIC TEST REPORT - NOT A PATIENT",font=font(40),fill="#142750")
draw.text((65,140),"Lipid panel | Report date: 2026-09-01",font=font(35),fill="black")
draw.text((65,220),"Test",font=font(32),fill="black")
draw.text((650,220),"Result",font=font(32),fill="black")
draw.text((880,220),"Unit",font=font(32),fill="black")
draw.text((1120,220),"Reference",font=font(32),fill="black")
for index,(name,value,range_) in enumerate([("Total cholesterol","230","<200"),("LDL cholesterol","152","<100"),("HDL cholesterol","48",">40"),("Triglycerides","165","<150")]):
    y=315+index*120
    for x,text in [(65,name),(650,value),(880,"mg/dL"),(1120,range_)]:draw.text((x,y),text,font=font(34),fill="black")
draw.text((65,890),"Fictional numbers for testing transcription only.",font=font(30),fill="#536479")
image.save(ROOT/"static/sample-report.png")
print("Generated icons and a synthetic test report.")
