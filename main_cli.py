# main_cli.py

import sys
import interfaces.cli.cli as cli


if __name__ == '__main__':
    cli.start_cli(len(sys.argv) == 1)