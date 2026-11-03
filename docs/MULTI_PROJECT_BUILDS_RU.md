# YadroKreator: физически и визуально независимые проекты

Huananzhi CORE 192.168.0.100 · Ubuntu Server 24.04 · 2 × Xeon E5-2650 · 48 ГБ DDR3 · RTX 3060.

## Правило производства

YadroKreator — общий **диспетчер** и веб-интерфейс. Но ни один проект не использует чужие исходники, каталоги заданий, Git-кеш, временные файлы, журналы, отчёты или образ. Вкладки интерфейса визуально помечены разными цветами и собственным путём, а история отфильтрована по типу проекта. Одна общая SQLite хранит только учёт заданий и блокировку занятости; это **не** общий каталог сборки.

| Вкладка | Проект | Операция | Результат |
|---|---|---|---|
| WIFICAM T23N | `musikfed/wificam_T23N` | Реальная MIPS Thingino/Buildroot сборка | Отдельный SD IMG, SHA256 и проверка MBR/FAT16/ext4 |
| Irila Baikal | `musikfed/Irila_baikal_v1.0` | Только проверка SHA-закреплённых исходников | Отдельный JSON-аудит (можно скачать с вкладки Irila) |
| WifCam Helper | `musikfed/wifcam_helper` | Тесты камеры в отдельной панели и разрешённый профиль для WIFICAM | Независимый тестовый JSON, опция `WIFICAM_WEBRTC=0|1` |
| Система | `musikfed/YadroKreator` | Обновление панели, перезапуск, остановка | Свой журнал обновления |

Полный Irila x86-64 Secure Boot IMG сейчас создаётся в [собственном GitHub Actions Irila](https://github.com/musikfed/Irila_baikal_v1.0/actions/workflows/build-installed-full-secureboot-img.yml). Кнопка аудита **не** запускает `sudo`, `losetup`, `mkfs` и не компилирует ядро. Для этого потребуется отдельный изолированный привилегированный сборщик с проверенными файловыми loop-устройствами, а не общая команда камеры.

## Новое размещение на Huananzhi

```text
/1tbdisk/PegineLab/
├── projects/
│   ├── YadroKreator/             # исходники самой веб-фабрики
│   ├── wificam_T23N/             # оригинальный проект камеры и эталон Thingino/
│   ├── Irila_baikal_v1.0/       # оригинальный проект Irila
│   └── wifcam_helper/           # независимый стенд
├── build/
│   ├── projects/
│   │   ├── wificam_T23N/
│   │   │   ├── git-cache/wificam_T23N.git/
│   │   │   ├── tmp/
│   │   │   ├── cache/ccache/
│   │   │   └── jobs/<job-id>/wificam_T23N/out/{candidate-sd,private-sd}/
│   │   └── Irila_baikal_v1.0/
│   │       ├── git-cache/Irila_baikal_v1.0.git/
│   │       ├── tmp/
│   │       ├── cache/ccache/
│   │       └── jobs/<job-id>/
│   │           ├── Irila_baikal_v1.0/
│   │           └── irila-source-audit.json
│   ├── locks/factory-build.lock # единственная общая блокировка
│   └── thingino-firmware/       # закреплённый upstream для T23N
└── factory-state/
    ├── factory.sqlite3          # общий учёт заданий, не сборочные файлы
    ├── projects/
    │   ├── wificam_T23N/
    │   │   ├── logs/<job-id>.log
    │   │   └── validation/<job-id>.json
    │   └── Irila_baikal_v1.0/
    │       └── logs/<job-id>.log
    └── update-logs/             # только обновления панели
```

**Точное имя проекта:** `wificam_T23N` с конечной буквой N. Пути `wificam_T23` и `wificam_T23N` в Linux не взаимозаменяемы.

## Общая очередь, но раздельные рабочие области

В SQLite активным считается только одно задание в статусе `queued`, `running`, `stopping`. Создание блокируется через `BEGIN IMMEDIATE`. Worker дополнительно захватывает `flock` `build/locks/factory-build.lock`. 32 потока и 48 ГБ памяти не являются основанием для безопасного параллельного запуска двух тяжёлых сборок.

Глобальная блокировка распространяется на **задачи YadroKreator**, но не на посторонние ручные `make` или другие CI runner. При полной остановке фабрики учтены и `peginelab-t23n-*`, и `peginelab-irila-*` user systemd units. Общий Linux/SSH/другие Docker-службы не останавливаются.

## Удаление старых результатов после перехода на новую структуру

Старое дерево `build/jobs/<id>` и журналы `factory-state/logs/<id>.log` **не копируются и не смешиваются** с новыми проектами. Пользователь разрешил удалить прежние результаты, но **обновление из GitHub никогда не удаляет их автоматически**. На самом сервере скрипт нужно запускать вручную.

**Важное отличие:** GitHub хранит Git-коммиты исходников и документацию. Сгенерированные локально `.bin`, `.img`, логи и секреты `wifi.env` **не обязательно находятся в GitHub**. Удаление единственного локального IMG может быть необратимым. Перед подтверждением смотрите список реальных файлов в dry-run.

```bash
cd /1tbdisk/PegineLab/projects/YadroKreator
# 1. Только показать, какие старые UUID-деревья/логи будут удалены:
python3 scripts/cleanup_legacy_builds.py

# 2. Если список подходит и сборка не идёт, явно удалить старые
#    ЗАВЕРШЁННЫЕ задания и их ранее сохранённые отчёты:
python3 scripts/cleanup_legacy_builds.py --apply --confirm DELETE-LEGACY-JOBS

# 3. Необязательно отдельно очистить старый ОБЩИЙ Git-кеш.
#    Новые раздельные кеши под build/projects/ не затрагиваются.
python3 scripts/cleanup_legacy_builds.py --prune-old-git-cache
python3 scripts/cleanup_legacy_builds.py --apply --confirm DELETE-LEGACY-JOBS --prune-old-git-cache
```

Защита сценария: проверяет глобальный `flock`, SQLite-статусы, UUID, старый `log_path`, не следует символическим ссылкам и не удаляет `projects/`, `build/projects/`, `build/thingino-firmware/`, `factory-state/factory.sqlite3`, `~/crt-cert/`, эталон `wificam_T23N/Thingino/thingino-t23-sd.bin` и данные других служб. После просмотра удаляются только старые строки SQLite и соответствующие им старые локальные файлы. Новые задания не затрагиваются.

Просто `git pull` или обновление панели через «Система» не является командой очистки и не запускает сборку.

## Разделение отчётов и скачивания

На вкладке WIFICAM доступны только проверенные образы T23N из её отдельной задачи. Вкладка Irila показывает только собственный аудит исходников и скачивает его как JSON, не как IMG. WifCam Helper остаётся независимым сервисом на `127.0.0.1:8765` (открывайте с ноутбука через SSH-туннель). Попытки передать Irila report в T23N image validator возвращают ошибку.

Автоматические GitHub CI проверки проверяют код и файловые границы; они не доказывают физическую загрузку камеры, Acer или звук из динамика.
