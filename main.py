import sys
import cli.cli


if __name__ == '__main__':
    cli.start_cli(len(sys.argv) == 1)