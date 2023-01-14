from getpass import getpass
import paramiko
from scp import SCPClient
import os
from PyPDF2 import PdfReader, PdfWriter

### SoC printer options
printer_list = ["psts", "pstsb", "pstsc", "psc008", "psc011"]

### Paramiko / SSH / scp parameters
host = "stu.comp.nus.edu.sg"
username = "e0271169"                                                                                                  # TODO: User input

### Printing parameters
filename = "testprint2"                                                                                                # TODO: User input
local_filepath = f"/home/theo/schoolwork/hnr2023/{filename}.pdf"        # [local]  file to print                       # TODO: User input
local_dest = "/home/theo/schoolwork/hnr2023/testfolder"                 # [local]  folder to store chunked files       # TODO: check for collision
remote_dest = "~/testfolderhnr2023"                                     # [remote] folder to store chunked files       # TODO: check for collision
tempname = "hnr2023"                                                                                                   # TODO: check for collision
printqueues = [p+"-sx" for p in printer_list[:3]]                       # printer list (default: psts, pstsb, pstsc)   # TODO: User input
printers = len(printqueues)


### File preprocessing (local)
pdf_reader = PdfReader(local_filepath)
pages = len(pdf_reader.pages)

fname = os.path.splitext(os.path.basename(local_filepath))[0]
if pages >= printers:
    per_printer = pages // printers
    for p in range(printers):
        pdf_writer = PdfWriter()
        p_start = p * per_printer
        p_end = pages if p == printers else p_start + per_printer
        for page in range(p_start, p_end):
            pdf_writer.add_page(pdf_reader.pages[page])
        output_filename = f'{local_dest}/{fname}_{p+1}.pdf'
        with open(output_filename, 'wb') as out:
            pdf_writer.write(out)


### Paramiko set up
client = paramiko.client.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(host, username=username, password=getpass())    
    
    
### Copy file over
scp_client = SCPClient(client.get_transport())
scp_client.put(local_dest, remote_dest, recursive=True)
    

### Convert all pdf files to PostScript    
pdf2ps = f"""for f in {remote_dest}/*.pdf; do
pdf2ps "$f" "${{f%.*}}.ps";
rm "$f";
done"""
_stdin, _stdout,_stderr = client.exec_command(pdf2ps)
print(_stdout.read().decode())
e = _stderr.read().decode()
if e:
    print(e)


### Make printing commands
lpr_commands = []
for p in printqueues:
    cmd = f"lpr -P {p} {remote_dest}/{filename}_{p}.ps"
    lpr_commands.append(cmd)
print_cmd = " & ".join(lpr_commands)

### Make queuecheck commands
# lpq_commands = []
# for p in printqueues:
#     cmd = f"lpr -P {p}"
#     lpq_commands.append(cmd)
# command = command + "&&" + " && ".join(lpq_commands)


### Print
_stdin, _stdout,_stderr = client.exec_command(print_cmd)
print(_stdout.read().decode())
e = _stderr.read().decode()
if e:
    print(e)


### Cleanup
cleanup_cmd = f"rm -r {remote_dest}"
_stdin, _stdout,_stderr = client.exec_command(cleanup_cmd)
print(_stdout.read().decode())
e = _stderr.read().decode()
if e:
    print(e)


# Paramiko's nonsense
_stdin.close()
client.close()

