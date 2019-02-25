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
alias ggf='echo'
alias ggfl='echo'
unalias ggsup

# Directories
alias lla="ls -la -G"
alias la="ls -a -G"
alias ls="ls -G"
alias lls="lla"

# Development
alias simplehttpserver="python -m http.server"
alias gr="grep-manual"
alias grl="grep-manual -l"
alias grc="gr --exclude='*.js' --exclude='*.css'"
alias grcl="grl --exclude='*.js' --exclude='*.css'"
alias bower="noglob bower"
alias cd_chrome_extensions="cd $HOME/Library/Application\ Support/Google/Chrome/Default/Extensions"
alias wifi_watch="sudo node ~/repos/wifi-watch/wifi-watch.js &"
alias phpstorm="pstorm"
alias simulator_android="~/Library/Android/sdk/emulator/emulator -avd Nexus_5X_API_28_x86 &"
alias simulator_ios="open -a Simulator"

# MySQL
alias mysql="/Applications/MAMP/Library/bin/mysql"
alias replace="/Applications/MAMP/Library/bin/replace"
alias mysqldump="/Applications/MAMP/Library/bin/mysqldump"

# Vars
export WORKON_HOME="~/.virtualenvs"
export EDITOR=mcedit
export PYTHONPATH="/usr/local/bin/python:$PYTHONPATH"

# direnv
# eval (direnv hook fish)         # fish direnv hook
# eval "$(direnv hook zsh)"       # zsh direnv hook

# virtualenv
# eval (python -m virtualfish)                    # fish virtualenv hook
# source /usr/local/bin/virtualenvwrapper.sh      # zsh virtualenv hook


# Output current folder name as terminal tab title
precmd () { echo -ne "\e]1;${PWD##*/}\a" }


# Set EXTENDED_GLOB to use excluding wildcards
setopt extendedglob
alias ssha="ssh-add ~/.ssh/^(*.pub|known_hosts|config)" # add all existing SSH certificates
