import os
import uuid
import random
import re
import fitz  # PyMuPDF
import pytesseract
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from ethiopian_date import EthiopianDateConverter
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# 1. QINDAA'INA FOLDAROOTAA
UPLOAD_FOLDER = "uploads"
IMG_FOLDER = "extracted_images"
CARD_FOLDER = "cards"
FONT_PATH = "fonts/AbyssinicaSIL-Regular.ttf"
TEMPLATE_PATH = "static/id_card_template.png"

for folder in [UPLOAD_FOLDER, IMG_FOLDER, CARD_FOLDER]:
    os.makedirs(folder, exist_ok=True)

# Render irratti tesseract path yoo barbaachise (Linux irratti deault dha)
# pytesseract.pytesseract.tesseract_cmd = r'/usr/bin/tesseract'

def clear_old_files():
    for folder in [UPLOAD_FOLDER, IMG_FOLDER, CARD_FOLDER]:
        for filename in os.listdir(folder):
            file_path = os.path.join(folder, filename)
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
            except Exception as e:
                print(f"Error deleting {file_path}: {e}")

# 2. LOGIC PDF IRRAA ODEEFFANNOO BAASUU
def extract_all_images(pdf_path):
    doc = fitz.open(pdf_path)
    image_paths = []
    for page_index in range(len(doc)):
        page = doc[page_index]
        for img_index, img in enumerate(page.get_images(full=True)):
            xref = img[0]
            base_image = doc.extract_image(xref)
            img_name = f"p{page_index}_i{img_index}_{uuid.uuid4().hex[:5]}.{base_image['ext']}"
            path = os.path.join(IMG_FOLDER, img_name)
            with open(path, "wb") as f:
                f.write(base_image["image"])
            image_paths.append(path)
    doc.close()
    return image_paths

def extract_pdf_data(pdf_path):
    doc = fitz.open(pdf_path)
    page = doc[0]
    full_text = page.get_text("text")
    
    # Asirratti Rect kee akkuma duraatti itti fuufa
    data = {
        "fullname": page.get_textbox(fitz.Rect(170.7, 218.6, 253.3, 239.2)).strip(),
        "dob": page.get_textbox(fitz.Rect(50, 290, 170, 300)).strip().replace("\n", " | "),
        "sex": page.get_textbox(fitz.Rect(50, 320, 170, 330)).strip().replace("\n", " | "),
        "nationality": page.get_textbox(fitz.Rect(50, 348, 170, 360)).strip().replace("\n", " | "),
        "phone": page.get_textbox(fitz.Rect(50, 380, 170, 400)).strip(),
        "region": page.get_textbox(fitz.Rect(150, 290, 253, 300)).strip(),
        "zone": page.get_textbox(fitz.Rect(150, 320, 320, 330)).strip(),
        "woreda": page.get_textbox(fitz.Rect(150, 350, 320, 400)).strip(),
        "fan": page.get_textbox(fitz.Rect(70, 220, 150, 230)).strip(),
    }
    doc.close()
    return data

def generate_card(data, image_paths):
    card = Image.open(TEMPLATE_PATH).convert("RGBA")
    draw = ImageDraw.Draw(card)
    
    # Dates
    now = datetime.now()
    gc_issued = now.strftime("%d/%m/%Y")
    eth = EthiopianDateConverter.to_ethiopian(now.year, now.month, now.day)
    ec_issued = f"{eth.day:02d}/{eth.month:02d}/{eth.year}"
    expiry_full = f"{now.day:02d}/{now.month:02d}/{now.year + 8} | {eth.day:02d}/{eth.month:02d}/{eth.year + 8}"

    # Image Processing (Simplified)
    if image_paths:
        p_raw = Image.open(image_paths[0]).convert("RGBA")
        p_large = p_raw.resize((310, 400))
        card.paste(p_large, (65, 200), p_large)

    # Fonts
    try:
        font = ImageFont.truetype(FONT_PATH, 37)
        small = ImageFont.truetype(FONT_PATH, 32)
    except:
        font = small = ImageFont.load_default()

    draw.text((405, 170), data["fullname"], fill="black", font=font)
    draw.text((405, 305), data["dob"], fill="black", font=small)
    draw.text((405, 375), data["sex"], fill="black", font=small)
    draw.text((1130, 240), data["region"], fill="black", font=small)
    draw.text((470, 500), data["fan"], fill="black", font=small)
    draw.text((405, 440), expiry_full, fill="black", font=small)

    out_path = os.path.join(CARD_FOLDER, f"id_{uuid.uuid4().hex[:6]}.png")
    card.convert("RGB").save(out_path)
    return out_path

# 3. TELEGRAM HANDLERS
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Akkam! PDF kee naaf ergi, ani gara Kaardii Faydaatti nan jijjiira.")

async def handle_docs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.document.mime_type == 'application/pdf':
        msg = await update.message.reply_text("PDF kee fudhadheera, hojjechaan jira... ⏳")
        
        file = await context.bot.get_file(update.message.document.file_id)
        pdf_path = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4().hex}.pdf")
        await file.download_to_drive(pdf_path)
        
        try:
            clear_old_files()
            imgs = extract_all_images(pdf_path)
            data = extract_pdf_data(pdf_path)
            card_path = generate_card(data, imgs)
            
            await update.message.reply_photo(photo=open(card_path, 'rb'), caption="Kunoo kaardii kee!")
            await msg.delete()
        except Exception as e:
            await update.message.reply_text(f"Dogoggora: {str(e)}")
    else:
        await update.message.reply_text("Maaloo fayila PDF qofa ergi.")

# 4. MAIN RUNNER
if __name__ == '__main__':
    # Token kee Render Environment Variable irraa fudhata
    TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "7959584708:AAGpNLV3H1kEGjvZg-ppu1-5rcRCjCzHeJc")
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_docs))
    
    print("Botichi hojii jalqabeera...")
    app.run_polling()