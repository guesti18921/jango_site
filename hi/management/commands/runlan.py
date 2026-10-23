"""Run the local site on Wi-Fi with explicit host validation and working static files."""
import ipaddress
import os
import socket

from django.conf import settings
from django.contrib.staticfiles.management.commands.runserver import Command as RunserverCommand
from django.core.management.base import CommandError

PRIVATE_NETWORKS = [ipaddress.ip_network(value) for value in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')]


def private_ipv4(value):
    try:
        address = ipaddress.ip_address(value)
        return address.version == 4 and any(address in network for network in PRIVATE_NETWORKS)
    except ValueError:
        return False


def discover_addresses():
    try:
        addresses = socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        addresses = []
    return sorted({address for address in addresses if private_ipv4(address)})


class Command(RunserverCommand):
    help = 'Start the website for computers on the same private Wi-Fi/LAN.'

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument('--ip', help='Private IPv4 of this computer, if autodetection fails.')
        parser.add_argument('--port', type=int, default=8000)

    def handle(self, *args, **options):
        if options['addrport'] or options['use_ipv6']:
            raise CommandError('Use runlan --port 8000 [--ip 192.168.1.10].')
        if not 1 <= options['port'] <= 65535:
            raise CommandError('Port must be between 1 and 65535.')
        address = options['ip']
        if address and not private_ipv4(address):
            raise CommandError('--ip must be a private IPv4 address, for example 192.168.1.10.')
        addresses = [address] if address else discover_addresses()
        if not addresses:
            raise CommandError('No Wi-Fi/LAN IPv4 found. Run ipconfig, then: python manage.py runlan --ip YOUR_IP')
        settings.ALLOWED_HOSTS = list(dict.fromkeys([*settings.ALLOWED_HOSTS, *addresses]))
        if os.environ.get('RUN_MAIN') != 'true':
            self.stdout.write(self.style.SUCCESS('Open on another computer connected to the same Wi-Fi:'))
            for address in addresses:
                self.stdout.write(f'  http://{address}:{options["port"]}/')
            self.stdout.write('Keep this terminal open. Stop with Ctrl+C.')
        options['addrport'] = f'0.0.0.0:{options["port"]}'
        return super().handle(*args, **options)
