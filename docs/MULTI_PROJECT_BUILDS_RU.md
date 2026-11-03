# Раздельные проекты сборки YadroKreator · T23N / Irila / Helper

## Назначение

Веб-интерфейс имеет разделы **WIFICAM T23N**, **Irila Baikal**, **WifCam Helper**, **Образы WIFICAM**, **Система**.

| Проект | GitHub | Папка исходников на CORE | Поддерживаемое действие |
|---|---|---|---|
| WIFICAM T23N | `musikfed/wificam_T23N` | `/1tbdisk/PegineLab/projects/wificam_T23N` | Полная сборка MIPS/Thingino в SD-кандидат, из отдельно закреплённого SHA |
| Irila Baikal | `musikfed/Irila_baikal_v1.0` | `/1tbdisk/PegineLab/projects/Irila_baikal_v1.0` | Изолированная Git-проверка исходников; сборка x86-64 Secure Boot IMG **отдельной GitHub Actions** |
| WifCam Helper | `musikfed/wifcam_helper` | `/1tbdisk/PegineLab/projects/wifcam_helper` | Стенд камеры, JSON-профиль `WIFICAM_WEBRTC=0|1`, по галочке в разделе WIFICAM |
| YadroKreator | `musikfed/YadroKreator` | `/1tbdisk/PegineLab/projects/YadroKreator` | Веб-панель, журнал, systemd workers, контроль статуса, выдача образа |

**Имя важно:** `wificam_T23N` с конечной **N**, не `wificam_T23`. Фабрика не пытается угадать, что это одна и та же папка, и не сливает их.

## Каталоги сборок

Рабочие копии ни одного Git-проекта не перезаписываются. Для каждой задачи `<job_id>` отдельный Git SHA и файловая система:
```text
/1tbdisk/PegineLab/
  build/
    git-cache/
      wificam_T23N.git/               # bare cache исходников камеры
      Irila_baikal_v1.0.git/          # другой bare cache исходников Irila
      fetch.lock                      # кратковременная Git-блокировка
    locks/factory-build.lock          # всего ОДНА активная worker задача
    jobs/<job_id>/
      wificam_T23N/out/candidate-sd/  # только T23N, когда профиль T23N
      wificam_T23N/out/private-sd/    # только T23N + локальная Wi-Fi конфигурация
      helper-preset.json              # только по галочке Helper
      Irila_baikal_v1.0/              # только когда Irila audit
      irila-source-audit.json         # результат НЕ является образом .img
  factory-state/
    factory.sqlite3
    logs/<job_id>.log
```

Точное имя UUID и `profile` фиксируется в SQLite. Артефакты камеры выбираются исключительно из T23N worktree успешного задания; при скачивании проверяются SHA256, MBR, LBA34, FAT16/uImage, ext4. Irila report — **JSON-аудит**, для него запрещены маршруты WIFICAM `/download`, `/validate`, `/layout.svg`.

## Одновременные сборки запрещены

Новый job для любой поддерживаемой операции не запускается, когда другая в статусе `queued`, `running` или `stopping`. Проверка и вставка в SQLite происходит в одной `BEGIN IMMEDIATE` транзакции. В worker независимо удерживается неблокирующий `flock` `build/locks/factory-build.lock`, так что повторный запуск user systemd worker с ошибкой завершится, а не затрёт shared Thingino кеш.

Ограничение распространяется **только на задачи фабрики**, не на вручную запущенный `make`, другую независимую systemd-службу или внешние GitHub Actions runner. Для любых ручных операций нужно отдельно проверять активность фабрики. Режим «параллельно» намеренно не предлагается до независимых buildroot/output/cache/cgroup memory quota. 48 ГБ ОЗУ и 2×Xeon не доказывают безопасность параллельных компиляций.

`stop-all` останавливает оба типа user units `peginelab-t23n-<id>` и `peginelab-irila-<id>`, помимо веб-панели и собственного таймера обновлений. Службы всего хоста, Docker daemon и другие проекты не трогаются.

## Irila: сборка образа != компиляция ядра T23N

Irila предназначена для Acer Swift 3 / Ryzen 3500U / x86-64 и использует *подписанное ядро Ubuntu*, не скрипт сборки Linux MIPS T23N. Её IMG конвейер использует `sudo`, `losetup`, `parted`, `mkfs` и `mount`. Такой конвейер **не исполняется веб-панелью**, где нет отдельного ограниченного root-helper и защиты целевых устройств. Кнопка «Проверить исходники Irila» получает `main` Git SHA, изолирует worktree и проверяет ожидаемые исходные скрипты/CI. Она не создаёт IMG и не делает вид, что компилирует ядро.

Для настоящего Irila IMG:
[Build Installed FULL Secure Boot IMG](https://github.com/musikfed/Irila_baikal_v1.0/actions/workflows/build-installed-full-secureboot-img.yml) — вручную Run workflow в GitHub Actions. IMG и SHA256 принадлежат Irila (не T23N/SD).

Будущий локальный режим требует отдельный изолированный root-сборщик с разрешёнными только loop из файла внутри per-job каталога, без физических устройств и с полноценной валидацией GPT/EFI/ext4/Secure Boot, квотами диска и отменой. До этой реализации **не выдавать кнопку «Собрать Irila IMG» как действующую**.

## Установка на Huananzhi

```sh
cd /1tbdisk/PegineLab/projects/YadroKreator
# После обновления через раздел «Система» появятся новые вкладки.
# Не запускайте два разных билда вручную в обход фабрики.
bash scripts/project-control.sh status
```

Web UI/CI также не могут подтвердить, что каталоги исходников уже физически клонированы на вашей Ubuntu; Irila Git source audit может получить ветку напрямую с GitHub в изолированный кеш, не сбрасывая ваш `projects/Irila_baikal_v1.0`. Для опции Helper профиль должен действительно присутствовать в соседнем `projects/wifcam_helper/profiles/t23n_lean.json`.

## Контроль

`python3 -m unittest discover -s tests -p 'test_*.py' -v` проверяет ограничения по проектам, атомарный запрет параллельных задач, отчёт Irila без T23N .img, Git-изоляцию, worker flock, повторную загрузку веб-интерфейса и остановку systemd. Это **программные** проверки — аппаратной сборки и загрузки Irila/Acer или камеры не выполняют.
