# Shared shell config — source from ~/.zshrc on each machine.
# Machine-specific secrets/paths: ~/.zshrc.local (not in git).

# Scripts (~/repos/shell-scripts/usr/bin → /usr/local/bin)
export PATH="/usr/local/bin:$PATH"
export PATH="$HOME/.local/bin:$PATH"

# Node (nvm)
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"

# git
unalias ggsup 2>/dev/null
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
alias ggundolast="git reset --soft HEAD~1"
alias gglines="git ls-files | xargs cat | wc -l"
alias gglastdiff="git diff HEAD^ HEAD -- . "

gggdeletebranch () {
  git branch -d $1
  git push origin --delete $1
}

folder_size () {
  du -sh "$@" | sort -hr
}

ssha() {
  find ~/.ssh -maxdepth 1 -type f \
    ! -name '*.pub' ! -name '*.pem' ! -name '*.old' \
    ! -name 'known_hosts' ! -name 'config' ! -name 'authorized_keys' \
    -exec ssh-add -q {} +
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

# direnv + venv prompt prefix
eval "$(direnv hook zsh)"

show_virtual_env() {
  if [[ -n "$VIRTUAL_ENV" && -n "$DIRENV_DIR" ]]; then
    echo "($(basename $VIRTUAL_ENV)) "
  fi
}
export show_virtual_env
PS1='$(show_virtual_env)'$PS1
