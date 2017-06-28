// Kills battery_watch process

var exec = require('child_process').exec;

exec('ps aux | grep battery_watch', function(error, stdout, stderr){
  try {
    var data = stdout.split(/\n/).map(function(str){
      return str.split(/\s+/);
    }).filter(function(items){
      return items.indexOf('node') > -1 || items.indexOf('sleepwatcher') > -1;
    });
    var pids = data.map(function(item){
      return data[1];
    });

    console.log('>>> pids', pids);
    //exec('kill -9 ' + pid);
  }
  catch (e) {}
});
