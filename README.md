# git-backup

Designed to collect all collaborators of a given github repository, search their repos for a fork of the given repo and clone if found.
The idea is to run as a nightly cron job to back up developer code and leaking IP that is not being pushed to their organization's repository.

## Usage
```
usage: git-backup.py [-h] [-u <username>] [--oauth <token>] [-o <path>]
                     [--fork_list_only] [-v] [--history <N>] [-p]
                     <repo>

github repo backup

positional arguments:
  <repo>                Repository to back up, e.g. spacetelescope/hstcal

optional arguments:
  -h, --help            show this help message and exit
  -u <username>, --user <username>
                        GitHub username
  --oauth <token>       GitHub OAuth token
  -o <path>             Backup directory (default "./")
  --fork_list_only      Only print the list of users with forks of <repo>
  -v, --verbose         Make verbose
  --history <N>         Number of backups to maintain in backup dir. Older
                        dirs will be checked and purged upon future backup
                        (default 0 => forever)
  -p, --purge_only      Only purge older backups
```

## Disclaimer
Not bullet proof
