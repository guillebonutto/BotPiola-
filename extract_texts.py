import os
from pypdf import PdfReader

pdf_files = [
    "11. Soportes y Resistencias, Tendencias.pdf",
    "12. Velas Japonesas.pdf",
    "13. Estados de Mercado.pdf",
    "14. Ondas de Elliot.pdf",
    "15. Chartismo.pdf",
    "16. Indicadores Técnicos.pdf",
    "17. Detallar una Estrategia.pdf",
    "18. Estrategias detalladas.pdf"
]

output_file = "pdf_strategies_content.txt"

with open(output_file, "w", encoding="utf-8") as f_out:
    for pdf_file in pdf_files:
        if os.path.exists(pdf_file):
            try:
                print(f"Extracting: {pdf_file}")
                reader = PdfReader(pdf_file)
                f_out.write(f"\n\n--- START OF {pdf_file} ---\n\n")
                for page in reader.pages:
                    text = page.extract_text()
                    if text:
                        f_out.write(text)
                        f_out.write("\n")
                f_out.write(f"\n\n--- END OF {pdf_file} ---\n\n")
            except Exception as e:
                print(f"Error reading {pdf_file}: {e}")
                f_out.write(f"Error reading {pdf_file}: {e}\n")
        else:
            print(f"File not found: {pdf_file}")

print("Extraction complete.")
