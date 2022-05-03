TABLES=$(mysql bumblebee -e 'SHOW TABLES')
RUNSQL='SET FOREIGN_KEY_CHECKS = 0;'
for TABLE in $(mysql -sN bumblebee -e 'SHOW TABLES;'); do
  RUNSQL="$RUNSQL DROP TABLE IF EXISTS $TABLE;"
done

RUNSQL="$RUNSQL SET FOREIGN_KEY_CHECKS = 1;"
mysql bumblebee -e "$RUNSQL"
