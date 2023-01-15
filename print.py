#!/usr/bin/python3

import argparse
import concurrent.futures
import multiprocessing
import os
import shutil
import sys

from getpass import getpass
from pathlib import Path

import paramiko

from scp import SCPClient
from PyPDF2 import PdfReader, PdfWriter

### general constants
AVAILABLE_PRINTERS = ("psts-sx", "pstsb-sx", "pstsc-sx", "psc008-sx", "psc011-sx", 
                      "psts-dx", "pstsb-dx", "pstsc-dx", "psc008-dx", "psc011-dx",
                      "psts-nb", "pstsb-nb", "pstsc-nb", "psc008-nb", "psc011-nb",)
HOST = "stu.comp.nus.edu.sg"

# ### thresholds
# PARALLEL_THRESHOLD = multiprocessing.cpu_count()


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
                        default=("psts-sx", "pstsb-sx", "pstsc-sx"),                        # default to level 1, single sided
                        help="printer selections", nargs="+") 
    parser.add_argument("files", metavar="F", type=str, nargs="+", help="files to print")

    return parser.parse_args()


### for setting up
def reset_local_dest(local_dest):
    try:
        os.makedirs(local_dest)
    except FileExistsError:
        shutil.rmtree(local_dest)
        os.makedirs(local_dest)


def get_ssh_cxn(host, username, passwd):
    client = paramiko.client.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=host, username=username, password=passwd)

    return client


def copy_chunks_to_remote(client, local_dest, remote_dest):
    scp_client = SCPClient(client.get_transport())
    cleanup_command = get_remote_cleanup_command(remote_dest)
    run_command_in_remote(client, cleanup_command)
    scp_client.put(local_dest, remote_dest, recursive=True)


### for obtaining shell commands
def get_remote_cleanup_command(remote_dest):
    command = f"""if [ -d {remote_dest} ]; 
    then rm -rf {remote_dest}; 
    fi;
    """

    return command


def get_pdf2ps_command(remote_dest):
    command = f"""for f in {remote_dest}/*.pdf; do
    pdf2ps "$f" "${{f%.*}}.ps";
    rm "$f";
    done"""

    return command


def get_print_command(print_queues, remote_dest, file_name):
    lpr_commands = []

    for idx, p in enumerate(print_queues):
        command = f"lpr -P {p} {remote_dest}/{file_name}_{idx}.ps"
        lpr_commands.append(command)

    # TODO : if the prints are not chunked (1-2 pages) - this will throw an lpr: cannot access error
    #        but the printing will still go as usual

    # launch in background for concurrency
    print_command = " & ".join(lpr_commands)

    return print_command


### for running shell commands on remote client
def run_command_in_remote(client, command):
    _stdin, _stdout, _stderr = client.exec_command(command)
    sys.stdout.write(_stdout.read().decode())

    e = _stderr.read().decode()
    if e:
        sys.stdout.write(e)

    _stdin.close()  # bypass issue with paramiko


### for local file preprocessing
def chunk_pdf(local_filepath, local_dest, file_name):
    file_path = os.path.join(local_filepath, f"{file_name}.pdf")
    pdf_reader = PdfReader(file_path)
    pages = len(pdf_reader.pages)

    num_printers = len(get_printing_args().printers)
    if pages >= num_printers:
        per_printer = pages // num_printers
        for p in range(num_printers):
            pdf_writer = PdfWriter()
            p_start = p * per_printer
            p_end = pages if p == (num_printers - 1) else p_start + per_printer
            for page in range(p_start, p_end):
                pdf_writer.add_page(pdf_reader.pages[page])
            output_filename = f'{local_dest}/{file_name}_{p}.pdf'
            with open(output_filename, 'wb') as out:
                pdf_writer.write(out)
    else:
        shutil.copy(file_path, os.path.join(local_filepath, f"{file_name}_1.pdf"))


### for overall file processing
def process_file(ssh_cxn, file, printers, local_files_path_str, local_dest_path_str, remote_dest_path_str):
    chunk_pdf(local_files_path_str, local_dest_path_str, file)
    copy_chunks_to_remote(ssh_cxn, local_dest_path_str, remote_dest_path_str)
    run_command_in_remote(ssh_cxn, get_pdf2ps_command(remote_dest_path_str))
    run_command_in_remote(ssh_cxn, get_print_command(printers, remote_dest_path_str, file))


# # returns unary function that takes in a file name and
# # does the processing for use in ProcessPoolExecutor
# def get_file_consumer(username, passwd, printers, local_files_path_str, local_dest_path_str, remote_dest_path_str):
#     def file_processor(file):
#         # create new ssh cxn for uploading
#         cxn = get_ssh_cxn(HOST, username, passwd)
#
#         # process the file
#         process_file(cxn, file, printers, local_files_path_str, local_dest_path_str, remote_dest_path_str)
#
#     return file_processor


### for cleaning up
def cleanup(client, local_dest, remote_dest):
    shutil.rmtree(local_dest)

    cleanup_command = get_remote_cleanup_command(remote_dest)
    run_command_in_remote(client, cleanup_command)

    client.close()


def main():
    # get necessary args
    printing_args = get_printing_args()
    username, passwd = get_login_args()

    # get path strs
    local_files_path_str = Path(printing_args.local_filepath).absolute()
    local_dest_path_str = os.path.join(local_files_path_str, printing_args.local_dest)
    remote_dest_path_str = printing_args.remote_dest

    # local dest preprocessing
    reset_local_dest(local_dest_path_str)

    # setup ssh cxn
    ssh_cxn = get_ssh_cxn(HOST, username, passwd)

    # remote dest preprocessing
    run_command_in_remote(ssh_cxn, get_remote_cleanup_command(remote_dest_path_str))

    # process files
    for file in printing_args.files:
        process_file(ssh_cxn, file, printing_args.printers, local_files_path_str,
                     local_dest_path_str, remote_dest_path_str)

    # # parallelize based on threshold
    # if len(printing_args.files) < PARALLEL_THRESHOLD:
    #     for file in printing_args.files:
    #         process_file(ssh_cxn, file, printing_args.printers, local_files_path_str,
    #                      local_dest_path_str, remote_dest_path_str)
    # else:
    #     # get file processor
    #     file_proc = get_file_consumer(username, passwd, printing_args.printers, local_files_path_str,
    #                                   local_dest_path_str,
    #                                   remote_dest_path_str)
    #
    #     # run with executor
    #     with concurrent.futures.ProcessPoolExecutor() as executor:
    #         for _ in executor.map(file_proc, printing_args.files):
    #             pass

    # run cleanup
    cleanup(ssh_cxn, local_dest_path_str, remote_dest_path_str)


if __name__ == "__main__":
    main()
