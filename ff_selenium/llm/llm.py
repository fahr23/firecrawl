# Description: This script processes the latest KAP notifications in the specified directory and sends them to local finance LLM API for analysis.
import os
from openai import OpenAI
from fpdf import FPDF

# Configuration
TEXT_FILES_DIR = "/root/kap_txts"  # Directory containing text files with KAP notifications
LLM_ANALYTICS_DIR = "/root/llm_analytics"  # Directory to store the generated analytics
client = OpenAI(base_url="http://host.docker.internal:1234/v1", api_key="lm-studio")
MODEL = "QuantFactory/Llama-3-8B-Instruct-Finance-RAG-GGUF"
MAX_TOKENS = 4096  # Maximum context length for the model
CHUNK_SIZE = 3000  # Chunk size to ensure we stay within the token limit
class PDF(FPDF):
    def __init__(self):
        super().__init__()
        self.add_font('DejaVu', '', '/workspaces/firecrawl/ff_selenium/llm/DejaVuSans.ttf', uni=True)
        self.add_font('DejaVu', 'B', '/workspaces/firecrawl/ff_selenium/llm/DejaVuSansBold.ttf', uni=True)
        self.add_page()
        self.set_font('DejaVu', '', 12)  # Use Unicode font

    def header(self):
        self.set_font('DejaVu', 'B', 12)  # Use Unicode font for the header
        self.cell(0, 10, 'BacktoFuture Responses', 0, 1, 'C')

    def footer(self):
        self.set_y(-15)
        self.set_font('DejaVu', '', 8)  # Use Unicode font for the footer
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

    def chapter_title(self, title):
        self.set_font('DejaVu', 'B', 12)  # Use Unicode font for the header
        self.set_text_color(255, 0, 0)  # Set text color to red
        self.cell(0, 10, title, 0, 1, 'L')
        self.ln(10)
        self.set_text_color(0, 0, 0)  # Reset text color to black


    def chapter_body(self, body):
        self.set_font('DejaVu', '', 12)  # Use Unicode font for body
        self.multi_cell(0, 10, body)
        self.ln()
# Ensure the font file is added to FPDF
# PDF().add_font('DejaVu', '', 'DejaVuSans.ttf', uni=True)

def send_to_chatgpt(conversation_history):
    """
    Sends the accumulated content of text files to ChatGPT API and retrieves the response.

    :param conversation_history: Accumulated content of the text files.
    :return: ChatGPT response.
    """
    try:
        messages = [
            {
                "role": "system",
                "content": (
                    "Kamu Aydınlatma Platformu (KAP) verilerini sana göndereceğim. "
                    "Türkçe olarak cevaplarını hazırla. "
                    "Verilen bildirimlerden yola çıkarak kısa ve orta vadeli yatırım yorumları yap. "
                    "Yatırım fırsatlarını değerlendir ve her yorumun yanında yatırımcılara yönelik "
                    "net tavsiyelerde bulun. Tavsiyelerinin dayandığı nedenleri açıkça belirt. "
                    "Cevaplarını Türkçe olarak hazırla ve finansal fırsatları detaylandır. "
                )
            },
            {"role": "user", "content": conversation_history}
        ]

        # Call the OpenAI API
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.7
        )
        
        # Extract and return the assistant's reply
        return response.choices[0].message
    except Exception as e:
        print(f"Error communicating with ChatGPT API: {e}")
        return None
def send_file_content(file_path, pdf):
    """
    Sends the content of a single file to ChatGPT API and writes the response to the PDF.

    :param file_path: Path to the text file.
    :param pdf: PDF object to write the response to.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            file_content = file.read()
            response = send_to_chatgpt(file_content)
            if response:
                url="https://www.kap.org.tr/tr/Bildirim/"
                file_path=os.path.basename(file_path).replace('.txt','')
                pdf.chapter_title(f"Response for file: {url+os.path.basename(file_path)}")
                pdf.chapter_body(response.content)
                pdf.add_page()
                print(f"Response for file: {os.path.basename(file_path)}")
                print(response.content)
                print("\n" + "="*50 + "\n")

            else:
                print(f"Failed to get a response for file: {os.path.basename(file_path)}")
    except Exception as e:
        print(f"Error reading {file_path}: {e}")

def process_latest_text_contents():
    """
    Processes the last 10 created text files in the specified directory.
    """
    files = [os.path.join(TEXT_FILES_DIR, f) for f in os.listdir(TEXT_FILES_DIR) if os.path.isfile(os.path.join(TEXT_FILES_DIR, f)) and f.endswith('.txt')]
    files.sort(key=os.path.getctime, reverse=False)
    latest_files = files[:2]
    # Print the file names
    print("Latest files:")
    for file in latest_files:
        print(file)

    conversation_history = ""
    for file_path in latest_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                conversation_history += file.read() + "\n"
        except Exception as e:
            print(f"Error reading {file_path}: {e}")

    if conversation_history:
        # Split conversation_history into chunks
        chunks = [conversation_history[i:i + CHUNK_SIZE] for i in range(0, len(conversation_history), CHUNK_SIZE)]
        
        pdf = PDF()

        for i, chunk in enumerate(chunks):
            response = send_to_chatgpt(chunk)
            if response:
                pdf.chapter_title(f"Response for chunk {i + 1}:")
                pdf.chapter_body(response.content)
                print(f"Response for chunk {i + 1}:")
                print(response.content)
                print("\n" + "="*50 + "\n")
                pdf.add_page()

            else:
                print(f"Failed to get a response for chunk {i + 1}.")

        pdf.output("ChatGPT_Responses.pdf")
    else:
        print("No content to send to ChatGPT.")

def process_latest_files():
    """
    Processes the last 10 created text files in the specified directory.
    """
    files = [os.path.join(TEXT_FILES_DIR, f) for f in os.listdir(TEXT_FILES_DIR) if os.path.isfile(os.path.join(TEXT_FILES_DIR, f)) and f.endswith('.txt')]
    files.sort(key=os.path.getctime, reverse=False)
    latest_files = files[:2]

    # Print the file names
    print("Latest files:")
    for file in latest_files:
        print(file)


    pdf = PDF()
    filename = "BacktoFuture_Responses"

    for file_path in latest_files:
        filename += "_" + os.path.basename(file_path).replace('.txt', '')
        send_file_content(file_path, pdf)

    filename += ".pdf"
    output_path = os.path.join(LLM_ANALYTICS_DIR, filename)
    pdf.output(output_path, 'F')



if __name__ == "__main__":
    # Process and send notifications to ChatGPT API
    process_latest_files()