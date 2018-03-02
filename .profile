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
alias ggresetfile="git checkout HEAD -- "
alias ggmerge="git merge"
alias ggtstash="git stash"
alias ggamend="git commit -a --amend"
alias ggundo="git reset HEAD~"
alias ggheroku="git push heroku master"

# Rewrite
unalias ggsup
alias ggf='echo'
alias ggfl='echo'

# Directories
alias lla="ls -la -G"
alias la="ls -a -G"
alias ls="ls -G"
alias lls="lla"

# Development
alias simplehttpserver="python -m SimpleHTTPServer"
alias gr="grep-manual"
alias grl="grep-manual -l"
alias grc="gr --exclude='*.js' --exclude='*.css'"
alias grcl="grl --exclude='*.js' --exclude='*.css'"
alias bower="noglob bower"
alias cd_chrome_extensions="cd $HOME/Library/Application\ Support/Google/Chrome/Default/Extensions"
alias wifi_watch="sudo node ~/repos/wifi-watch/wifi-watch.js &"
alias phpstorm="pstorm"

# MySQL
alias mysql="/Applications/MAMP/Library/bin/mysql"
alias replace="/Applications/MAMP/Library/bin/replace"
alias mysqldump="/Applications/MAMP/Library/bin/mysqldump"

# Vars
source /usr/local/bin/virtualenvwrapper.sh
export WORKON_HOME="~/.virtualenvs"
export EDITOR=mcedit

# direnv hook
eval "$(direnv hook zsh)"
