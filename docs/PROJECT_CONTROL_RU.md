# YadroKreator — запуск / остановка панели, не сборок

**Что контролируем:** только веб-панель `peginelab-factory.service` на
Huananzhi Ubuntu 24.04 (`http://192.168.0.100:62404/`). Это отдельная
служба `systemd --user`; никаких Docker, sudo, reboot, остановки SSH или
запущенных `peginelab-build-*` задач.

## На Huananzhi (Linux / SSH)

Из checkout `/1tbdisk/PegineLab/projects/YadroKreator`:

```bash
bash start.sh                             # запустить / Start
bash stop.sh                              # остановить / Stop
bash scripts/project-control.sh status    # статус / Status
```

Если исполняемые права не выставлены GitHub — используйте `bash`, как выше.
Скрипты работают только от **того же обычного Ubuntu-пользователя**, что
выполнял `bash install.sh`; от `root` запуск запрещён. Если службы ещё
нет, скрипт не создаёт её автоматически (первый раз используйте
`bash install.sh`).

**Остановка панели НЕ отменяет сборку прошивки**, выполняющуюся отдельным
systemd user unit. Для остановки задания используйте штатную кнопку
«Остановить» у конкретной сборки **до** выключения панели. После
`stop.sh` сайт исчезнет и не сможет сам себя запустить: старт через SSH
либо локальный терминал Huananzhi.

## С Windows PowerShell (через SSH на Ubuntu)

С компьютера, который видит `192.168.0.100`:

```powershell
.\start.ps1                       # запустить Linux-сервис по SSH
.\stop.ps1                        # остановить Linux-сервис по SSH
.\scripts\project-control.ps1 -Action status
```

Можно задать сервер: `.\start.ps1 -Server 'user@192.168.0.100'`.
Режим по умолчанию `BatchMode=yes` — для скрипта нужен настроенный
SSH-ключ; сначала проверьте `ssh user@192.168.0.100` с Windows.
Скрипт не хранит и не спрашивает пароль в коде.

## Для текущей камеры

Остановка YadroKreator **не выключает T23N**: камера загружена с SD
`/dev/mmcblk0p2` и её отдельный PegineLab WIFICAM на порту
`:8090` ещё требует аппаратной проверки CGI.
YadroKreator — это сервер **сборки**, не робот и не работающая камера.
