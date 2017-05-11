import argparse
import pycurl
import subprocess
import sys
import json
from io import BytesIO
from getpass import getpass

class Auth:
    def __init__(self):
        self.username = None
        self.password = None
    
    def login(self):
        print('username:')
        try:
            self.username = raw_input()
        except NameError:
            self.username = input()
            
        self.password = getpass(); 
        print('')

def getCurl(buffer, credentials, url):
    
    c = pycurl.Curl()
    #c.setopt(c.URL, 'https://api.github.com/zen')
    c.setopt(c.URL, url)
    c.setopt(c.USERNAME, credentials.username)
    c.setopt(c.PASSWORD, credentials.password)
    c.setopt(c.WRITEDATA, buffer)
    c.perform()
    c.close()
        
def getCollaborators(credentials, repo):
    
    url = 'https://api.github.com/repos/' + str(repo) + '/collaborators'
    buffer = BytesIO()
    getCurl(buffer, credentials, url)

    body = buffer.getvalue().decode('iso-8859-1')   
    return json.loads(body)

def getUsers(credentials, repo):
    users = set()
    collab = getCollaborators(credentials, repo)
    for user in collab:
        users.add(user['login'])
        
    return users

class Input:
    def __init__(self, _argv):
        self.argv = _argv
        self.repo = None
        
    def parse(self):
        parser = argparse.ArgumentParser(description='github repo backup')
        parser.add_argument(dest='repo', metavar='<repo>', nargs=1, type=str,
                             help='Repository to back up, e.g. spacetelescope/hstcal', default=None)
        args = parser.parse_args(self.argv)
    
        if args.repo == None:
            print('ERROR: No repo sepecified')
            return 1
        else:
            self.repo = args.repo[0] 

def main(argv):
      
    input = Input(argv)
    input.parse()
    
    print('Backing up {0}...'.format(input.repo))
    
    credentials = Auth()
    credentials.login()
       
    users = getUsers(credentials, input.repo)
    print('{0} users found as collaborators of {1}'.format(len(users), input.repo))
    
    for user in users:    
        print(user)
    
if __name__ == "__main__":
    main(sys.argv[1:])