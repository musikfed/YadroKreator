# YadroKreator — полный запуск / STOP проекта

YadroKreator на Huananzhi использует **нативный user systemd**, а не
Docker Compose. Прежний `stop.sh` выключал лишь `peginelab-factory.service`,
оставляя сборки и таймер. Исправлено: теперь `bash stop.sh` означает
**полную остановку собственного проекта**.

## Выполнение на Huananzhi Ubuntu пользователем user

```bash
cd /1tbdisk/PegineLab/projects/YadroKreator
bash stop.sh
bash scripts/project-control.sh status
# Позднее, когда проект снова понадобится:
bash start.sh
```

**Полный STOP** останавливает следующие **только проектные** ресурсы:

- `peginelab-factory.service` (Waitress/Flask, порт 62404) — останавливается
  и **отключается автозапуск после reboot/SSH**;
- временные пользовательские `peginelab-t23n-<job id>.service` с
  компиляцией; сборка может быть **прервана без нового готового образа**;
- временные `peginelab-factory-update-<id>.service` (отдельные
  проверки GitHub) и `peginelab-panel-*.*` от старого управления;
- `peginelab-factory-update.timer` и его `service`, если
  опциональный таймер включён. Сохраняется признак, чтобы
  `start.sh` включил его снова **только если он был включён**;
- контейнеры Docker или Podman **только с точной меткой**
  `com.peginelab.project=YadroKreator` либо
  `com.docker.compose.project=yadrokreator`. Штатный YadroKreator
  вообще не создаёт контейнеров. Непомеченные контейнеры **не трогаем**.
  Если права на Docker/Podman отсутствуют — выводится предупреждение,
  вместо ложного сообщения о полном выключении.

`start.sh` включает веб-службу и при необходимости ранее подключённый
таймер; **не возобновляет принудительно отменённые сборки** и не поднимает
старые контейнеры. Сохраняет SQLite, журналы, Git, артефакты прошивок.

**НЕ выключаются:** операционная система Ubuntu, служба systemd
в целом, Docker/Podman daemon, SSH, WireGuard/VPN, роботы, камеры,
другие приложения или контейнеры. Ни `pkill`, ни `killall`,
ни `docker stop $(docker ps -q)` в коде нет.

**Особенность старой установки:** если отдельно существует системный
`peginelab-t23n-build.service` (без `--user`), скрипт честно
выведет WARNING и предложит явно выполнить от администратора
`sudo systemctl stop peginelab-t23n-build.service` **на Huananzhi**.
Никаких автоматических sudo внутри скрипта нет.

Для выключения **только сайта**, без сборок и таймера:
```bash
bash scripts/project-control.sh stop-panel
```

## Windows PowerShell

Из локального checkout YadroKreator на Windows:
```powershell
.\stop.ps1                       # полный STOP на Huananzhi по SSH
.\start.ps1                      # запуск веб-панели и ранее включённого таймера
.\scripts\project-control.ps1 -Action status
```
При необходимости: `-Server user@192.168.0.100`. Все операции выполняются
в Ubuntu, не в Windows. OpenSSH сам запросит пароль или использует ключи.

## Веб-интерфейс 62404

Кнопка **«Остановить весь проект»** в «Обзор» / «Система» вызывает
отдельную user-systemd задачу для `bash scripts/project-control.sh stop`.
Работающую сборку разрешено прерывать **только после второго
подтверждения**. Команда доступна лишь через разрешённую LAN/VPN
и same-origin заголовок. Без персонального логина **не выставляй 62404
в Интернет**.

После STOP веб-сайт пропадёт. Через него снова нажать START невозможно,
поэтому потребуется SSH или локальный терминал Huananzhi и `bash start.sh`.

Существующая кнопка **«Система → Проверить обновления → Обновить»**
по-прежнему служит для GitHub fast-forward обновления. Для обновления
не нужно выключать проект, и активная сборка блокирует обновление.

## Проверка фактического результата

```bash
systemctl --user is-active peginelab-factory.service
systemctl --user is-enabled peginelab-factory.service
systemctl --user list-units --all --type=service 'peginelab-*'
systemctl --user list-timers --all 'peginelab-*'
ss -ltnp | grep :62404 || echo "Веб-порт закрыт"
```

Если ты запустил **ручной** `make` в отдельном shell (не из
YadroKreator), это не проектный systemd unit. `stop.sh` его не
угадывает и не должен массово убивать другие компиляторы.
