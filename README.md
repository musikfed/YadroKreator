# PegineLab YadroKreator — Firmware & Kernel Factory

**Самостоятельная станция сборки Linux-ядер и прошивок на Ubuntu 24.04.**

**Independent Linux kernel and firmware build station for Ubuntu 24.04.**

Проект полностью отделён от исходников камеры `wificam_T23N`. Веб-интерфейс, SQLite, systemd-управление, документация и макеты принадлежат этому репозиторию. WIFICAM — лишь первый внешний профиль сборки.

## Первый профиль / First build target

- **WIFICAM T23N**: внешний checkout `musikfed/wificam_T23N` и Thingino на том же Linux-хосте.
- Последующие профили Linux kernel, ARM, MIPS, RISC-V можно добавлять без изменений в репозиторий камеры.
- Web server: **Waitress + Flask**, native Ubuntu build on ext4, **no Docker**.
- Port: **192.168.0.100:62404** (внутренний IP сервера владельца).
- Доступ через существующую VPN/LAN **без веб-пароля**, по выбору владельца.
- История и статусы сборок в SQLite WAL; фоновые задачи запускает systemd.

## Проверенный образ и новые кандидаты / Baseline versus build candidates

- Аппаратно загруженный `wificam_T23N/Thingino/thingino-t23-sd.bin` — неизменяемая ссылка на `0.1_test` (**SD boot подтверждён, старый Web UI не исправлен**).
- При обычной сборке в панели (`PUBLISH=0`) новый `out/candidate-sd/thingino-t23-sd.bin` считается **непроверенным кандидатом** до испытаний на реальной камере.
- При локальном `local/wifi.env` Wi-Fi ключ встроен в `out/private-sd/thingino-t23-sd.bin`; такие образы не публикуются.
- Панель показывает наличие и SHA256 всех трёх вариантов отдельно. Новый SD image нельзя автоматически объявлять релизом.

## Документация

- [Русская инструкция](docs/README_RU.md)
- [English guide](docs/README_EN.md)
- [Превью главной панели](docs/previews/factory-overview.svg)
- [Превью страницы сборок](docs/previews/factory-builds.svg)

**Сетевая безопасность.** Веб-панель управляет запуском процессов и не содержит собственной аутентификации. Адрес 192.168.x.x **не** гарантирует изоляцию: используйте доверенную VPN, изолированную LAN и/или firewall. **Не публикуйте TCP 62404 в Интернет.** Для других установок можно использовать TLS и внешнюю аутентификацию.

**Build safety:** сборщик не публикует личные SD-образы с Wi-Fi ключом в GitHub (`PUBLISH=0`); образ не отдаётся по HTTP; прошивку нужно тестировать на устройстве.

© PegineLab. Сторонние компоненты сохраняют собственные лицензии и авторство.
