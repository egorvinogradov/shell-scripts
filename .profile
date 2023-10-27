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
alias ggdiff="git diff"
alias ggcommit="git commit -am"
alias ggadd="git add"
alias ggreset="git reset --hard"
alias ggresetfile="git checkout HEAD -- "
alias ggmerge="git merge"
alias ggtstash="git stash"
alias ggamend="git commit -a --amend"
alias ggundo="git reset HEAD~"
alias gglines="git ls-files | xargs cat | wc -l"

gggdeletebranch () {
  git branch -d $1
  git push origin --delete $1
}

folder_size () {
  du -sh "$@" | sort -hr
}

ssha() {
  find ~/.ssh -type f ! -name "*.pub" ! -name "*.pem" ! -name "*.old" ! -name "known_hosts" ! -name "config" -exec ssh-add {} \;
}

cheat () {
  curl "cheat.sh/$1"
}

zoom_join () {
  open "zoommtg://zoom.us/join?confno=$1"
}

unlock_hosts() {
  echo "Unlocking hosts file..."
  sudo chflags nouchg /etc/hosts
  sudo chflags noschg /etc/hosts
  sublime /etc/hosts
}

lock_hosts() {
  echo "Locking hosts file..."
  sudo chflags uchg /etc/hosts
  sudo chflags schg /etc/hosts
}

# Directories
alias lla="ls -lha -G"
alias la="ls -a -G"
alias ls="ls -G"
alias lls="lla"

# Development
alias simplehttpserver="python3 -m http.server"
alias cd_chrome_extensions="cd $HOME/Library/Application\ Support/Google/Chrome/Default/Extensions"

# Enable divenv
eval "$(direnv hook zsh)"

# Show virtualenv name when using direnv
show_virtual_env() {
  if [[ -n "$VIRTUAL_ENV" && -n "$DIRENV_DIR" ]]; then
    echo "($(basename $VIRTUAL_ENV)) "
  fi
}
export show_virtual_env
PS1='$(show_virtual_env)'$PS1

# Open Interpreter
export OPENAI_API_KEY=
