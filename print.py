import argparse
import os
import shutil

import paramiko

from getpass import getpass

from scp import SCPClient
from PyPDF2 import PdfReader, PdfWriter


### general constants
AVAILABLE_PRINTERS = ("psts-sx", "pstsb-sx", "pstsc-sx")
NUM_PRINTERS = len(AVAILABLE_PRINTERS)
HOST = "stu.comp.nus.edu.sg"

### for obtaining args
def get_login_args():
    username = input("stu username: ")
    passwd = getpass("stu password: ")

    return username, passwd


def get_printing_args():
    parser = argparse.ArgumentParser(description="Print at NUS SOC in parallel")

    # add path arguments
    parser.add_argument("-lf", "--local_filepath", required=True, type=str,
                        help="path to folder containing files to print")
    parser.add_argument("-ld", "--local_dest", type=str, default="chunks", help="subdir to store chunked files")
    parser.add_argument("-rd", "--remote_dest", type=str, default="~/par_temp",
                        help="path to remote dir to store chunked files")

    # add other arguments
    parser.add_argument("-p", "--printers", choices=AVAILABLE_PRINTERS,
                        default=AVAILABLE_PRINTERS,
                        help="printer selections")  # single sided for now
    parser.add_argument("files", metavar="F", type=str, nargs="+", help="files to print")

    return parser.parse_args()


### for setting up
def reset_local_dest(local_dest):
    try:
        os.makedirs(local_dest)
    except FileExistsError:
        shutil.rmtree(local_dest)
        os.makedirs(local_dest)


def get_ssh_client(host, username, passwd):
    client = paramiko.client.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=host, username=username, password=passwd)

    return client


def copy_chunks_to_remote(client, local_dest, remote_dest):
    scp_client = SCPClient(client.get_transport())
    scp_client.put(local_dest, remote_dest, recursive=True)


### for obtaining shell commands
def get_remote_preprocess_command(remote_dest):
    command = f"""if [ -d {remote_dest} ]; then
    rm -f {remote_dest} ; 
    fi; 
    mkdir -p {remote_dest}; 
    """

    return command


def get_pdf2ps_command(remote_dest):
    command = f"""for f in {remote_dest}/*.pdf; do
    pdf2ps "$f" "${{f%.*}}.ps";
    rm "$f";
    done"""

    return command


def get_print_command(print_queues, remote_dest, files):
    lpr_commands = []

    for file in files:
        for p in print_queues:
            command = f"lpr -P {p} {remote_dest}/{file}_{p}.ps"
            lpr_commands.append(command)

    # launch in background for concurrency
    print_command = " & ".join(lpr_commands)

    return print_command


def get_cleanup_command(remote_dest):
    return f"rm -r {remote_dest}"


### for running shell commands on remote client
def run_command_in_remote(client, command):
    _stdin, _stdout, _stderr = client.exec_command(command)
    print(_stdout.read().decode())

    e = _stderr.read().decode()
    if e:
        print(e)

    _stdin.close()  # bypass issue with paramiko


### for local file preprocessing
def chunk_pdf(local_filepath, local_dest, file_name):
    file_path = os.path.join(local_filepath, f"{file_name}.pdf")
    pdf_reader = PdfReader(file_path)
    pages = len(pdf_reader.pages)

    fname = os.path.splitext(os.path.basename(local_filepath))[0]
    if pages >= NUM_PRINTERS:
        per_printer = pages // NUM_PRINTERS
        for p in range(NUM_PRINTERS):
            pdf_writer = PdfWriter()
            p_start = p * per_printer
            p_end = pages if p == NUM_PRINTERS else p_start + per_printer
            for page in range(p_start, p_end):
                pdf_writer.add_page(pdf_reader.pages[page])
            output_filename = f'{local_dest}/{fname}_{p}.pdf'
            with open(output_filename, 'wb') as out:
                pdf_writer.write(out)


### for cleaning up
def cleanup(client, local_dest, remote_dest):
    shutil.rmtree(local_dest)

    cleanup_command = get_cleanup_command(remote_dest)
    run_command_in_remote(client, cleanup_command)

    client.close()


# ### SoC printer options
# printer_list = ["psts", "pstsb", "pstsc", "psc008", "psc011"]
#
# ### Paramiko / SSH / scp parameters
# host = "stu.comp.nus.edu.sg"
# username = "e0271169"  # TODO: User input
#
# ### Printing parameters
# filename = "testprint3"  # TODO: User input
# local_filepath = f"/home/theo/schoolwork/hnr2023/{filename}.pdf"  # [local]  file to print                       # TODO: User input
# local_dest = "/home/theo/schoolwork/hnr2023/testfolder"  # [local]  folder to store chunked files       # TODO: check for collision
# remote_dest = "~/testfolderhnr2023"  # [remote] folder to store chunked files       # TODO: check for collision
# tempname = "hnr2023"  # TODO: check for collision
# printqueues = [p + "-sx" for p in printer_list[:3]]  # printer list (default: psts, pstsb, pstsc)   # TODO: User input
# printers = len(printqueues)

def main():
    # get necessary args
    printing_args = get_printing_args()
    username, passwd = get_login_args()

    # local dest preprocessing
    local_filepath = printing_args.local_filepath
    local_dest = os.path.join(local_filepath, printing_args.local_dest)
    reset_local_dest(local_dest)

    # setup ssh client
    ssh_client = get_ssh_client(HOST, username, passwd)

    # process and print the files
    for file in printing_args.files:
        chunk_pdf(local_filepath, local_dest, file)
        copy_chunks_to_remote(ssh_client, local_dest, printing_args.remote_dest)
        run_command_in_remote(ssh_client, get_pdf2ps_command(printing_args.remote_dest))
        run_command_in_remote(ssh_client, get_print_command(printing_args.printers, printing_args.remote_dest, local_dest))

    # run cleanup
    cleanup(ssh_client, local_dest, printing_args.remote_dest)


if __name__ == "__main__":
    main()







