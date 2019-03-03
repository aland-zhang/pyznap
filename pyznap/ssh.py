"""
    pyznap.ssh
    ~~~~~~~~~~~~~~

    ssh connection.

    :copyright: (c) 2018-2019 by Yannick Boetzel.
    :license: GPLv3, see LICENSE for more details.
"""

import os
import logging
import subprocess as sp
from datetime import datetime
from .utils import exists


class SSHException(Exception):
    """General ssh exception to be raised if anything fails"""
    pass


class SSH:
    """SSH class.

    Attributes
    ------
    logger : {logging.logger}
        logger to use
    user : {str}
        User to use
    host : {str}
        Host to connect to
    key : {str}
        Path to keyfile
    port : {int}
        Port number to connect to
    socket : {str}
        Path to socket file (used with '-o ControlPath')
    cmd : {list of str}
        ssh command to use with subprocess
    """

    def __init__(self, user, host, key=None, port=22, compress=None):
        """Initializes SSH class.

        Parameters
        ----------
        user : {str}
            User to use
        host : {str}
            Host to connect to
        key : {str}, optional
            Path to keyfile (the default is None, meaning the standard location
            '~/.ssh/id_rsa' will be checked)
        port : {int}, optional
            Port number to connect to (the default is 22)

        Raises
        ------
        FileNotFoundError
            If keyfile does not exist
        SSHException
            General exception raised if anything goes wrong during ssh connection        
        """

        self.logger = logging.getLogger(__name__)

        self.user = user
        self.host = host
        self.port = port
        self.socket = '/tmp/pyznap_{:s}@{:s}:{:d}_{:s}'.format(self.user, self.host, self.port, 
                      datetime.now().strftime('%Y-%m-%d_%H:%M:%S'))
        self.key = key or os.path.expanduser('~/.ssh/id_rsa')

        if not os.path.isfile(self.key):
            self.logger.error('{} is not a valid ssh key file...'.format(self.key))
            raise FileNotFoundError(self.key)

        self.cmd = ['ssh', '-i', self.key, '-o', 'ControlMaster=auto', '-o', 'ControlPersist=1m',
                    '-o', 'ControlPath={:s}'.format(self.socket), '-p', str(self.port), 
                    '{:s}@{:s}'.format(self.user, self.host)]

        # try to connect to set up ssh connection
        try:
            sp.check_output(self.cmd + ['ls'], timeout=10, stderr=sp.PIPE)
        except sp.CalledProcessError as err:
            self.logger.error('Error while connecting to {:s}@{:s}: {}...'
                              .format(self.user, self.host, err.stderr.rstrip()))
            self.close()
            raise SSHException(err.stderr.rstrip())
        except sp.TimeoutExpired as err:
            self.logger.error('Error while connecting to {:s}@{:s}: {}...'
                              .format(self.user, self.host, err))
            self.close()
            raise SSHException(err)

        # set up compression
        self.setup_compress(compress)


    def setup_compress(self, _type):
        """Checks if compression algo is available on source and dest, creates cmd_compress command 
        to use for send/recv.

        Parameters
        ----------
        _type : {str}
            Type of compression to use
        """

        self.compression = None
        self.cmd_compress = self.cmd

        if _type == None:
            return

        algos = ['gzip', 'lzop', 'bzip2', 'pigz', 'xz']
        compress_cmd = {'gzip': 'gzip', 'lzop': 'lzop', 'bzip2': 'bzip2', 'pigz': 'pigz', 'xz': 'xz'}
        decompress_cmd = {'gzip': 'gzip -d', 'lzop': 'lzop -d', 'bzip2': 'bzip2 -d', 'pigz': 'pigz -d', 
                          'xz': 'xz -d'}

        if _type not in algos:
            self.logger.warning('Compression method {:s} not supported. Will continue without...'.format(_type))
            return

        # check if compression is available on source and dest
        if not exists(_type):
            self.logger.warning('Compression algo {:s} does not exist, continuing without compression...'
                           .format(_type))
            return
        if not exists(_type, ssh=self):
            self.logger.warning('Compression algo {:s} does not exist on {:s}@{:s}, continuing'
                        'without compression...'.format(_type, self.user, self.host))
            return

        self.compression = _type
        self.cmd_compress = [compress_cmd[_type]] + ['|'] + self.cmd + [decompress_cmd[_type]] + ['|']


    def close(self):
        """Closes the ssh connection by invoking '-O exit' (deletes socket file)"""

        try:
            sp.check_output(self.cmd + ['-O', 'exit'], timeout=5, stderr=sp.PIPE)
        except (sp.CalledProcessError, sp.TimeoutExpired):
            pass


    def __del__(self):
        self.close()
