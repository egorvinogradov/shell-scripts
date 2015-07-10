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

alias realsync="perl /usr/local/realsync/realsync"
alias simplehttpserver="python -m SimpleHTTPServer"

alias gr="grep-manual"
alias grl="grep-manual -l"
alias grc="gr --exclude='*.js' --exclude='*.css'"
alias grcl="grl --exclude='*.js' --exclude='*.css'"

alias chrome_extensions="cd $HOME/Library/Application\ Support/Google/Chrome/Default/Extensions"

alias bower="noglob bower"

alias runtest="premiere/testing/run_tests.bsh"
alias migrate="workon leadgenius && python premiere/manage.py migrate"
alias srvgrunt="source .envrc && grunt serve"


# Vars
export EDITOR=mcedit



# --------------------
# Remote Ubuntu server
# --------------------

# alias ls="ls --color=auto"
# alias lla="ls -la"
# alias grep="grep --color=auto"
