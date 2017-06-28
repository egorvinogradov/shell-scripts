var exec = require('child_process').exec;


var BATTERY_LIMIT_WARNING = 45;
var BATTERY_LIMIT_SLEEP = 44;

var warning_showed = false;

setInterval(function(){
  console.log('-');
  isAwake(function(awake){
    if (awake) {
      console.log('awake');
      getBatteryStatus(function(error, percentage, isDischarging){
        console.log(isDischarging ? 'discharging' : 'NOT discharging', percentage);
        if (!error && isDischarging) {
          if (percentage <= BATTERY_LIMIT_WARNING && !warning_showed) {
            exec('osascript -e \'display notification "Low battery level"\'');
            warning_showed = true;
          }
          else if (percentage <= BATTERY_LIMIT_SLEEP) {
            exec('osascript -e \'display notification "Putting computer to sleep in 1 minute"\'; sleep 30; pmset sleepnow', function(){
              warning_showed = false;
            });
          }
        }
        if (percentage > BATTERY_LIMIT_WARNING) {
          warning_showed = false;
        }
      });
    }
  });

}, 10 * 1000);


function isAwake(callback){
  exec('source ~/.battery_watch/status; echo $BATTERY_WATCH', function(error, stdout, stderr){
    if (!error && +stdout === 1) {
      callback(true);
    }
    else {
      callback(false);
    }
  });
}

function getBatteryStatus(callback){
  exec('pmset -g batt', function(error, stdout, stderr){
    try {
      var data = stdout.split(/\n/)[1].split(/;\s+/);
      var percentage = +data[0].replace(/^.*\s+([0-9]+)%$/, '$1');
      var isDischarging = data[1] === 'discharging';
      callback(false, percentage, isDischarging);
    }
    catch (e) {
      callback(true);
    }
  });
}

// fix waking up again (when not charging)
// run on startup


