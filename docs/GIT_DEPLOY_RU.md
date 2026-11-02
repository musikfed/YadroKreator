# GitHub → YadroKreator → T23N SD: без ручного копирования

**Источник:** `musikfed/wificam_T23N`, по умолчанию ветка **`mymarrchWFcam`**.
**Станок:** Ubuntu 24.04 на Huananzhi, `http://192.168.0.100:62404/`.
**Веб-панель:** отдельный `musikfed/YadroKreator/main`.
Это инструкция для сервера, не доказательство, что он уже развёрнут.

## Первый запуск на сервере (один раз)

Под обычным пользователем Ubuntu (не sudo), на разделе ext4:

```bash
sudo apt-get update
sudo apt-get install -y git python3-venv python3-pip make gcc g++ curl   e2fsprogs dosfstools fdisk lzop unzip rsync ccache
mkdir -p /1tbdisk/PegineLab/projects
git clone https://github.com/musikfed/YadroKreator.git /1tbdisk/PegineLab/projects/YadroKreator
cd /1tbdisk/PegineLab/projects/YadroKreator
bash bootstrap.sh
```

`bootstrap.sh` получает из GitHub закреплённый Thingino
`9925f46f73b9c39ec8d2a65134b18c94e6fdfb97` в
`/1tbdisk/PegineLab/build/thingino-firmware`, затем запускает установщик
веб-панели с тестами и user-systemd. Если существующий checkout Thingino
изменён локально, скрипт откажется удалять или заменять эти изменения.
Для Buildroot могут понадобиться дополнительные стандартные Ubuntu-пакеты:
ориентируйтесь на логи конкретной сборки.

## Пересобрать mymarrchWFcam через браузер

1. Открыть `http://192.168.0.100:62404/` **из доверенной LAN/VPN**.
2. Перейти в «Сборки» и выбрать **`mymarrchWFcam`**.
3. Нажать «Новая сборка» и подтвердить загрузку исходников из Git.
4. На сервере автоматически: `git fetch` ветки из **фиксированного**
   `https://github.com/musikfed/wificam_T23N.git` → получение commit SHA →
   отдельный detached Git worktree → Thingino/Buildroot → SD-кандидат.
5. Журнал, SHA исходников, размер и checksum кандидата будут в панели.

Старый checkout `projects/wificam_T23N` не переключается, не сбрасывается и
не очищается. Один и тот же bare Git-кэш ускоряет повторные сборки; каждая
задача использует свой собственный неизменяемый Git SHA.

```text
/1tbdisk/PegineLab/
├── projects/YadroKreator/            # панель, отдельный Git main
├── projects/wificam_T23N/            # существующая старая копия — не меняем
├── build/git-cache/wificam_T23N.git   # bare cache источников
├── build/jobs/<job-id>/wificam_T23N/  # фиксированный Git SHA и кандидат SD
├── build/thingino-firmware/          # pinned upstream, общий build cache
└── factory-state/                    # SQLite WAL и build logs
```

Новый образ ветки `mymarrchWFcam` помещается в *отдельный каталог задачи*;
для этой старой ветки результат внутри worktree называется
`Thingino/thingino-t23-sd.bin`. Ветка `main` пишет
`out/candidate-sd/thingino-t23-sd.bin`. Это **новые, ещё не проверенные
на камере образы**, а не замена `0.1_test`. При наличии серверного
`projects/wificam_T23N/local/wifi.env` он переносится в worktree автоматически,
с правами 0600: результат приватный, `PUBLISH=0` не отправляет его в GitHub.
Панель не скачивает бинарные файлы по HTTP.

**Не выполнять автоматическое `dd` на SD**. Следующий `0.2_test` можно
объявлять проверенным только после записи на карту с LBA0 и аппаратной проверки
загрузки, SSH, API/CGI, `:8090`, видео, PTZ и восстановления связи.

## Обновление и откат YadroKreator из GitHub

В разделе **Система → Обновления и восстановление**: «Проверить обновления», «Обновить панель», «Откатить предыдущую версию». При открытой странице проверка идёт каждые 15 минут, не устанавливая код автоматически. При активной сборке обновление и откат запрещены. Система сохраняет предыдущий успешный Git SHA и при ошибке установки пытается вернуть прежнюю ревизию. История SQLite, Thingino и SD-образы не переключаются. Операции идут в отдельных systemd user-unit, независимо от веб-браузера.

Откат возможен только после успешного обновления новой функцией; версия до установки этой функции не регистрируется как rollback автоматически.

Из существующего checkout:

```bash
cd /1tbdisk/PegineLab/projects/YadroKreator
bash deploy.sh --check  # проверить доступный commit main
bash deploy.sh --apply  # обновить из Git, тесты, restart веб-панели
bash deploy.sh --rollback  # вернуться к предыдущей успешной версии
```

Команда `--apply` не создаёт и не запускает прошивку и не перезапускает
Ollama. Она **откажется** от обновления, если обнаружит локальные изменения,
неожиданный origin, diverged ветку или выполняющуюся сборку.

При необходимости явно включить автоматическую проверку `main`
раз в 15 минут (выключена по умолчанию):

```bash
bash setup-update-timer.sh enable
# отключить:
bash setup-update-timer.sh disable
```

Таймер **только проверяет** GitHub: никакой автоматической установки и перезапуска. Новая версия отображается как уведомление в разделе «Система» (пока открыт браузер). Поставить обновление или откатить его можно только отдельным подтверждением. История SHA и последнего обновления хранится в `factory-state/updates.json`. Включать этот режим только
после первой ручной установки и проверки сервера. GitHub Actions проверяют
синтаксис, API и тестовый Git-кэш, но **не доказывают аппаратную сборку**.

**Безопасность:** веб-панель не требует пароль и способна запускать код из
доверенного Git-репозитория. TCP 62404 должен быть закрыт от WAN и ограничен
VPN/firewall для доверенных администраторов. Не добавляйте SSH-пароли, токены,
личные `.env`, Wi-Fi PSK и секреты в GitHub.
