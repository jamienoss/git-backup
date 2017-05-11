import argparse
import datetime
from getpass import getpass
from io import BytesIO
import json
import os
import shutil
import subprocess
import sys

import pycurl


class Session:
    api = 'https://api.github.com/'

    def __init__(self):
        self.username = None
        self.password = None
        self.oauthToken = None
        self.c = pycurl.Curl()

    def __del__(self):
        self.c.close()

    def login(self, username=None, oAuthToken=None):
        if username == None:
            print('github username:')
            try:
                self.username = raw_input()
            except NameError:
                self.username = input()
        else:
            self.username = username
        self.c.setopt(self.c.USERNAME, self.username)

        if oAuthToken:
            self.oAuthToken = oAuthToken
            self.c.setopt(self.c.PASSWORD, self.oAuthToken)
        else:
            self.password = getpass();
            self.c.setopt(self.c.PASSWORD, self.password)

    def checkError(self, response):
        if not response:
            return

        try:
            if response[0]['message'] == 'Bad credentials':
                sys.exit('ERROR: {0}'.format(response['message']))
        except KeyError:
            pass

    def checkHTTP(self):
        respCode = self.c.getinfo(self.c.RESPONSE_CODE)
        if respCode >= 400:
            sys.exit('ERROR: http {0}'.format(respCode))

    def zenTest(self):
        url = os.path.join(self.api, 'zen')
        return self.doCurl(url)

    def doCurl(self, url, keepAlive=True):
        buffer = BytesIO()
        self.c.setopt(self.c.URL, url)
        self.c.setopt(self.c.WRITEDATA, buffer)
        self.c.perform()
        self.checkHTTP()

        if not keepAlive:
            self.c.close()

        return buffer.getvalue().decode('iso-8859-1')

    def getCurl(self, url, keepAlive=True):
        body = self.doCurl(url, keepAlive)
        response = json.loads(body)
        self.checkError(response)
        return response

    def getCollaborators(self, repo):
        url = os.path.join(self.api, 'repos', str(repo), 'collaborators')
        return self.getCurl(url)

    def getUsers(self, repo):
        users = set()
        response = self.getCollaborators(repo)
        for user in response:
            users.add(user['login'])
        return users

    def hasRepo(self, user, searchRepo):
        url = os.path.join(self.api, 'users', user, 'repos')
        response = self.getCurl(url)
        for repo in response:
            if repo['name'] == searchRepo:
                return True

class Input:
    def __init__(self, _argv):
        self.argv = _argv
        self.repo = None
        self.username = None
        self.backupDir = './'
        self.oauthToken = None
        self.verbose = False
        self.printForkListOnly = False
        self.history = 0
        self.purgeOnly = False
        self.oAuthToken = None

    def parse(self):
        parser = argparse.ArgumentParser(description='github repo backup')
        parser.add_argument(dest='repo', metavar='<repo>', nargs=1, type=str,
                             help='Repository to back up, e.g. spacetelescope/hstcal', default=self.repo)
        parser.add_argument('-u', '--user', metavar='<username>', dest='username', nargs=1,
                             help='GitHub username', default=self.username)
        parser.add_argument('--oauth', metavar='<token>', dest='oAuthToken', nargs=1,
                             help='GitHub OAuth token', default=self.oAuthToken)
        parser.add_argument('-o', metavar='<path>', dest='backupDir', nargs=1,
                             help='Backup directory (default "./")', default=self.backupDir)
        parser.add_argument('--fork_list_only', dest='printForkListOnly', action='store_true', default=self.printForkListOnly,
                             help='Only print the list of users with forks of <repo>')
        parser.add_argument('-v', '--verbose', dest='verbose', action='store_true', default=self.verbose,
                             help='Make verbose')
        parser.add_argument('--history', metavar='<N>', dest='history', nargs=1, default=self.history, type=int,
                             help='Number of backups to maintain in backup dir. Older dirs will be checked and purged upon future backup (default 0 => forever)')
        parser.add_argument('-p', '--purge_only', dest='purgeOnly', action='store_true', default=self.purgeOnly,
                             help='Only purge older backups')
        args = parser.parse_args(self.argv)

        if args.repo == None:
            print('ERROR: No repo sepecified')
            return 1
        else:
            self.repo = args.repo[0]
            if (self.repo[-1] == '/'):
                self.repo = self.repo[:-1]

        if args.username:
            self.username = args.username[0]

        if args.oAuthToken:
            self.oAuthToken = args.oAuthToken[0]

        self.backupDir = args.backupDir[0]
        self.verbose = args.verbose
        self.printForkListOnly = args.printForkListOnly
        if args.history:
            self.history = int(args.history[0])
        self.purgeOnly = args.purgeOnly

def timeStamp(fmt='%Y-%m-%d'):
    return datetime.datetime.now().strftime(fmt)

def gitClone(repo):
    github = 'https://github.com'
    fullRepo = os.path.join(github, repo) + '.git'
    response = subprocess.run(['git', 'clone', fullRepo], shell=False, check=False, universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def backupRepo(dir, repo):
    currentPath = os.getcwd()
    try:
        os.mkdir(dir)
    except FileExistsError:
        sys.exit('ERROR: file exists "{0}"'.format(dir))
    except OSError as err:
        sys.exit('ERROR: {0}'.format(err))

    os.chdir(dir)
    gitClone(repo)
    os.chdir(currentPath)

def doBackup(input):
    repoOrg, repoName = os.path.split(input.repo)

    session = Session()
    if input.username:
        session.login(username=input.username, oAuthToken=input.oAuthToken)
    else:
        session.login()

    # Test credentials before doing anything else
    session.zenTest()

    print('Finding all collaborator forks...')
    users = session.getUsers(input.repo)
    print('{0} users found as collaborators of {1}'.format(len(users), input.repo))
    usersToBackup = set()
    for user in users:
        if input.verbose:
            print('    ' + user)

        if session.hasRepo(user, repoName):
            usersToBackup.add(user)

    print('{0} collaborators have forks of {1}'.format(len(usersToBackup), repoName))

    if input.printForkListOnly:
        for user in usersToBackup:
            print('    ' + user)
        return

    try:
        os.mkdir(input.backupDir)
    except FileExistsError:
        pass
    todaysDir = os.path.join(input.backupDir, timeStamp())
    try:
        os.mkdir(todaysDir)
    except FileExistsError:
        sys.exit('ERROR: file exists "{0}"'.format(todaysDir))

    # First backup root repository
    currentDir = os.path.join(todaysDir, repoOrg)
    print('Backing up "{0}" to {1}...'.format(input.repo, currentDir))
    backupRepo(currentDir, input.repo)

    # backup all user forks of repo
    print('Backing up all collaborator forks...')
    for user in usersToBackup:
        currentDir = os.path.join(todaysDir, user)
        repo = os.path.join(user, repoName)
        print('    Backing up "{0}" to "{1}"...'.format(repo, currentDir))
        backupRepo(currentDir, repo)

    print('Backup complete')

def doPurge(input):

    if (input.history == 0):
        print('Nothing to purge')
        return

    # purge older backups
    # hmmm not sure of the semantics here but this'll do

    dirList = os.listdir(input.backupDir)
    backupList = list()
    for entry in dirList:
        fullPath = os.path.join(input.backupDir, entry)
        if os.path.isdir(fullPath):
            backupList.append(fullPath)

    backupList.sort()
    length = len(backupList) - input.history
    print('Purging older backups...')
    if length <= 0:
        print('Nothing to purge')
        return
    toPurge = backupList[:length]

    for dir in toPurge:
        print('    ..."{0}"'.format(dir))
        try:
            shutil.rmtree(dir, ignore_errors=False)
        except OSError as err:
            print('WARNING: purge failure - {0}'.format(err))

    print('Purge complete')

def main(argv):

    input = Input(argv)
    input.parse()

    print('\n\n\n{0}'.format(timeStamp(fmt='%Y-%m-%d-%H-%M-%S')))

    if not input.purgeOnly:
        try:
            doBackup(input)
        except OSError as err:
            sys.exit('ERROR: {0}'.format(err))
        except:
            raise

    try:
        doPurge(input)
    except OSError as err:
        sys.exit('ERROR: {0}'.format(err))
    except:
        # add proper error handling and logging etc
        raise

if __name__ == "__main__":
    main(sys.argv[1:])
