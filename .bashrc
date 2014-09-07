# ---------
# Local Mac
# ---------

# git
alias ggbranch="git branch"
alias ggcheckout="git checkout"
alias ggfetch="git fetch"
alias gglog="git log"
alias ggstatus="git status"
alias ggpull="git pull origin"
alias ggpush="git push origin"
alias ggdiff="git diff"
alias ggcommit="git commit -am"
alias ggadd="git add"
alias ggreset="git reset --hard"
alias ggmerge="git merge"

# Directories
alias lla="ls -la -G"
alias la="ls -a -G"
alias ls="ls -G"
alias lls="lla"

# Development
alias runserver="python manage.py runserver"
alias realsync="perl /usr/local/realsync/realsync"
alias simplehttpserver="python -m SimpleHTTPServer"

alias gr="grep-manual . -r"
alias grl="grep-manual . -rl"
alias cgr="grep-manual . -r --exclude='*demos*' --exclude='*compiled*' --exclude='*libs*'"
alias cgrl="grep-manual . -rl --exclude='*demos*' --exclude='*compiled*' --exclude='*libs*'"

# Vars
export EDITOR=mcedit

# --------------------
# Remote Ubuntu server
# --------------------

alias runserver="fuser -k 9999/tcp; python ~/amazinghiring/frontend/apps/ah/manage.py runserver 0.0.0.0:9999"
alias ls="ls --color=auto"
alias lla="ls -la"
alias grep="grep --color=auto"
