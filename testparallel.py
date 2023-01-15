import paramiko

import time

from getpass import getpass
from multiprocessing import Pool
from typing import List


def _create_single_cxn(host: str, username: str, passwd: str) -> paramiko.client.SSHClient:
    client = paramiko.client.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=host, username=username, password=passwd)

    return client


def create_cxns(host: str, username: str, passwd: str, num_printers: int, cxn_limit: int, pool_size: int = 5) -> List[
    paramiko.client.SSHClient]:
    num_cxns = min(num_printers, cxn_limit)

    start = time.time()

    # cxns = [_create_single_cxn(host, username, passwd) for _ in range(num_cxns)]

    with Pool(pool_size) as pool:
        promises = [pool.apply_async(_create_single_cxn, args=(host, username, passwd)) for _ in range(num_cxns)]
        cxns = [promise.get() for promise in promises]

    end = time.time()

    print(f"Elapsed time: {end - start}")

    return cxns


def test():
    host = "stu.comp.nus.edu.sg"
    username = "e0271169"
    passwd = getpass()

    cxns = create_cxns(host, username, passwd, 5, 200)


if __name__ == "__main__":
    test()