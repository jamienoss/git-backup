import argparse
import datetime
from getpass import getpass
from io import BytesIO
import json
import os
import re
import shutil
import subprocess
import sys
import timeit

import pycurl

class HttpError(Exception):
    def __init__(self, _code, _message):
        self.code = _code
        self.message = _message

    def str(self):
        return 'http {0} - {1}'.format(self.code, self.message)

class Session:
    api = 'https://api.github.com/'

    def __init__(self):
        self.username = None
        self.password = None
        self.oauthToken = None
        self.c = pycurl.Curl()
        self.nPages = 1
        self.parseHeaderFlag = False
        self.requestCount = 0

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

        # Test credentials before doing anything else
        self.zenTest()

    def getErrorMessage(self, response):
        if not response:
            return
        try:
            return response['message']
        except KeyError:
           return None

    def checkError(self, response):
        respCode = self.c.getinfo(self.c.RESPONSE_CODE)

        if respCode >= 400:
            raise HttpError(respCode, self.getErrorMessage(response))

    def zenTest(self):
        url = os.path.join(self.api, 'zen')
        body = self.doCurl(url)
        if body:
            try:
                body = json.loads(body)
            except json.JSONDecodeError:
                pass
        self.checkError(body)
        return body

    def parseHeader(self, headerLine):
        if not self.parseHeaderFlag:
            return
        headerLine = headerLine.decode('iso-8859-1')
        self.getNPages(headerLine)

    def getNPages(self, headerLine):
        # To do: convert header to dict
        if ':' not in headerLine:
            return
        name, value = headerLine.split(':', 1)
        if name == 'Link':
            regex = re.search('page=([0-9]+)>; rel="last"', value)
            if regex:
                self.nPages = int(regex.group(1))
            else:
                self.nPages = 1
            return

    def doCurl(self, url, keepAlive=True, parseHeader=True):
        buffer = BytesIO()
        self.c.setopt(self.c.URL, url)
        self.c.setopt(self.c.WRITEDATA, buffer)
        self.c.setopt(self.c.HEADERFUNCTION, self.parseHeader)
        self.c.setopt(self.c.FOLLOWLOCATION, True)
        self.parseHeaderFlag = parseHeader
        self.c.perform()
        self.requestCount += 1

        if not keepAlive:
            self.c.close()

        return buffer.getvalue().decode('iso-8859-1')

    def getCurl(self, url, keepAlive=True):
        response = list()
        url = url + '?per_page=100'  # Lower the total number of requests
        body = self.doCurl(url, keepAlive=True, parseHeader=True)
        if body:
            body = json.loads(body)
        self.checkError(body)
        response.extend(body)

        if self.nPages == 1:
            if not keepAlive:
                self.c.close()
            return response

        # There are more pages to GET
        for page in range(2, self.nPages + 1):  # +1 := '<=' self.nPages rather than '<'
            body = self.doCurl(url + '&page=' + str(page), keepAlive=True, parseHeader=False)
            if body:
                body = json.loads(body)
            self.checkError(body)
            response.extend(body)

        if not keepAlive:
            self.c.close()
        return response

    def getCollaborators(self, repo):
        url = os.path.join(self.api, 'repos', str(repo), 'collaborators')
        return self.getCurl(url)

    def getUsers(self, repo):
        users = list()
        response = self.getCollaborators(repo)
        for user in response:
            users.append(user['login'])
        users.sort()
        return users

    def getOrgRepos(self, org):
        url = os.path.join(self.api, 'orgs', org, 'repos')
        response = self.getCurl(url)
        repos = list()
        for repo in response:
            repos.append(repo['name'])
        repos.sort()
        return repos

    def getRepos(self, user):
        url = os.path.join(self.api, 'users', user, 'repos')
        return self.getCurl(url)

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
        self.org = False
        self.ignore = []

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
        parser.add_argument('--org', dest='org', action='store_true',
                             help='Treats positional argument <repo> as a git organization to backup', default=self.org)
        parser.add_argument('--fork_list_only', dest='printForkListOnly', action='store_true', default=self.printForkListOnly,
                             help='Only print the list of users with forks of <repo>')
        parser.add_argument('-v', '--verbose', dest='verbose', action='store_true', default=self.verbose,
                             help='Make verbose')
        parser.add_argument('--history', metavar='<N>', dest='history', nargs=1, default=self.history, type=int,
                             help='Number of backups to maintain in backup dir. Older dirs will be checked and purged upon future backup (default 0 => forever)')
        parser.add_argument('-p', '--purge_only', dest='purgeOnly', action='store_true', default=self.purgeOnly,
                             help='Only purge older backups')
        parser.add_argument('--ignore', dest='ignore', default=self.ignore, nargs='*',
                             help="When using --org, list repos to ignore (don't backup)")
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

        self.ignore = args.ignore
        self.backupDir = args.backupDir[0]
        self.verbose = args.verbose
        self.printForkListOnly = args.printForkListOnly
        self.org = args.org

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

def createDirTree(root, repoOrg, repoName):
    # File hiarachy - :backDir/:timestamp/:org/:repo/:user
    todaysDir = os.path.join(root, timeStamp())
    orgDir = os.path.join(todaysDir, repoOrg)
    repoDir = os.path.join(orgDir, repoName)
    try:
        os.mkdir(root)
    except FileExistsError:
        pass
    try:
        os.mkdir(todaysDir)
    except FileExistsError:
        pass
    try:
        os.mkdir(orgDir)
    except FileExistsError:
        pass
    try:
        os.mkdir(repoDir)
    except FileExistsError:
        sys.exit('ERROR: file exists "{0}"'.format(repoDir))
    return repoDir

def doBackup(input, session, gitCache, repoOrg, repoName):
    fullRepo = os.path.join(repoOrg, repoName)
    print('Finding all collaborator forks for "{0}"...'.format(fullRepo))
    try:
        users = session.getUsers(fullRepo)
    except:
        # At least backup root repo
        if not input.printForkListOnly:
            repoDir = createDirTree(input.backupDir, repoOrg, repoName)
            currentDir = os.path.join(repoDir, repoOrg)
            print('Backing up "{0}" to "{1}"...'.format(fullRepo, currentDir))
            backupRepo(currentDir, fullRepo)
        raise

    print('{0} users found as collaborators of {1}'.format(len(users), fullRepo))
    usersToBackup = list()

    for user in users:
        if input.verbose:
            print('    ' + user)

        if user not in gitCache.userRepos:
            gitCache.addUserRepos(user, session.getRepos(user))

        if gitCache.userHasRepo(user, repoName):
            usersToBackup.append(user)

    usersToBackup.sort()
    print('{0} collaborators have forks of {1}'.format(len(usersToBackup), repoName))

    if input.printForkListOnly:
        for user in usersToBackup:
            print('    ' + user)
        return

    repoDir = createDirTree(input.backupDir, repoOrg, repoName)

    # First backup root repository
    currentDir = os.path.join(repoDir, repoOrg)
    print('Backing up "{0}" to "{1}"...'.format(fullRepo, currentDir))
    backupRepo(currentDir, fullRepo)

    # backup all user forks of repo
    print('Backing up all collaborator forks...')
    for user in usersToBackup:
        currentDir = os.path.join(repoDir, user)
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

class GitCache:
    def __init__(self):
        self.userRepos = {}  # to store JSON response from https://api.github.com/user/:user/repos

    def addUserRepos(self, user, repos):
        if user not in self.userRepos:
            self.userRepos[user] = repos

    def getUserRepos(self, user):
        return self.userRepos.get(user)

    def userHasRepo(self, user, searchRepo):
        repoInfo = self.getUserRepos(user)
        if not repoInfo:
            return None
        for repo in repoInfo:
            if repo['name'] == searchRepo:
                return True

def main(argv):

    start = timeit.default_timer()

    input = Input(argv)
    input.parse()

    print('\n\n\n{0}'.format(timeStamp(fmt='%Y-%m-%d-%H-%M-%S')))

    gitCache = GitCache()

    if not input.purgeOnly:
        session = Session()
        if input.username:
            session.login(username=input.username, oAuthToken=input.oAuthToken)
        else:
            session.login()

        repoList = list()
        if input.org:
            repoOrg = input.repo
            print('Treating "{0}" as git organization.'.format(repoOrg))
            repoList = session.getOrgRepos(repoOrg)
            for repo in input.ignore:
                try:
                    repoList.remove(repo)
                    print('WARNING: ignoring "{0}" from backup (--ignore)'.format(repo))
                except:
                    continue
        else:
            repoOrg, repoName = os.path.split(input.repo)
            repoList.append(repoName)

        for repo in repoList:
            try:
                doBackup(input, session, gitCache, repoOrg, repo)
            except HttpError as err:
                print(err.str())
                print('WARNING: skipping "{0}"'.format(os.path.join(repoOrg, repo)))
                pass


        print('\nSummary:')
        print('Total number of requests made: {0}'.format(session.requestCount))
        print('Total number of collaborators with forked IP of "{0}": {1}'.format(input.repo, len(gitCache.userRepos)))
        for user in gitCache.userRepos:
            print('    {0}'.format(user))

    doPurge(input)

    print('Total wallclock time taken: {0} (seconds)'.format(timeit.default_timer() - start))


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except OSError as err:
        sys.exit('ERROR: {0}'.format(err))
    except HttpError as err:
        sys.exit('ERROR: {0}'.format(err.str()))
    except:
        # add proper error handling and logging etc
        raise
