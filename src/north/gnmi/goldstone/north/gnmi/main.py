"""gNMI server runner."""


import logging
import argparse
from .server import serve
from .repo.sysrepo import Sysrepo


logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-p", "--secure-port", type=int, default=51051)
    parser.add_argument("-i", "--insecure-port", type=int)
    parser.add_argument(
        "-k",
        "--private-key-file",
        type=str,
        help="path to a PEM-encoded private key file",
    )
    parser.add_argument(
        "-c",
        "--certificate-chain-file",
        type=str,
        help="path to a PEM-encoded certificate chain file",
    )
    parser.add_argument(
        "supported_models_file",
        metavar="supported_models_file",
        help="path to a JSON file which is listed yang models supported by the gNMI server",
    )
    args = parser.parse_args()

    fmt = "%(levelname)s %(module)s %(funcName)s l.%(lineno)d | %(message)s"
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format=fmt)
    else:
        logging.basicConfig(level=logging.INFO, format=fmt)

    serve(
        Sysrepo,
        secure_port=args.secure_port,
        insecure_port=args.insecure_port,
        private_key_file=args.private_key_file,
        certificate_chain_file=args.certificate_chain_file,
        supported_models_file=args.supported_models_file,
    )


if __name__ == "__main__":
    main()
