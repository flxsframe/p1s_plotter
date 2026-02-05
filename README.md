# Handwriting Synthesis on Bambulab 3D-Printer

### Overview:
This code wirelessly synthesizes handwriting using a BambuLab 3D printer.
It processes a tablet-recorded character set in `JSON` format, converts it into `G-code`, and uploads the generated files via the BambuLab API.

### Usage:
- Use **Python 3.12** or higher.
- Make sure all the necessary libraries are installed.
- Enable **LAN-Only mode** on your BambuLab printer. (Required for wireless upload via the BambuLab API)
- Change the print variables to suit your printer. Defaults are set for the BambuLab P1S.
- Make sure you are connected to the same network as your printer — check the connection with OrcaSlicer or an equivalent tool.
- Run the script to save the G-code and send it to the printer.
- The G-code is saved in your project folder.

### Warnings and Considerations:
- Printers other than BambuLab may not work due to different pause and homing commands.
- Copying formatted text with font attributes directly into the text input may cause encoding errors with BytesIO.
- **DO NOT RUN CUSTOM G-CODE ON YOUR PRINTER WITHOUT CONSTANT SUPERVISION!**
- **THIS SOFTWARE CAN SEVERELY DAMAGE YOUR 3D PRINTER — USE AT YOUR OWN RISK!**
