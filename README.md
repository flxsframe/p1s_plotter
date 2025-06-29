# HANDWRITING SYNTHESIS ON BAMBULAB 3D PRINTER

OVERVIEW:
This code wirelessly synthesizes handwriting using a BambuLab 3D printer.
It processes a tablet-recorded character set in JSON format, converts it into G-code, and uploads the generated files via the BambuLabs API.

USAGE:
- Use Python 3.12 or higher, optionally in a Conda environment.
- Make sure you have all the necessary libraries installed.
- Enable LAN-Only mode on your BambuLab printer for connection with the API.
- Change the print variables to suit your printer. Defaults are set for the BambuLab P1S.
- Make sure you are within range of your printer — check the connection with OrcaSlicer or an equivalent tool.
- Run the script to save the G-code and send it to the printer.
- The G-code is saved in your project folder.

WARNINGS & CONSIDERATIONS:
- Printers other than BambuLab may have different pause and homing commands.
- Copying formatted text with font attributes directly into the text input may cause encoding errors with BytesIO.
- DO NOT RUN CUSTOM G-CODE ON YOUR PRINTER WITHOUT CONSTANT SUPERVISION.
- THIS SOFTWARE CAN SEVERELY DAMAGE YOUR 3D PRINTER—USE AT YOUR OWN RISK.
