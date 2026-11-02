# Разработка и выпуск релизов YadroKreator / WIFICAM

## Два независимых Git-репозитория

- \`musikfed/YadroKreator\` — только веб-панель, система сборок, визуализация, тесты, документация.
- \`musikfed/wificam_T23N\` — только исходники камеры, kernel config/Thingino overlays, драйверы, Web UI самой камеры, скрипты SD упаковки. \`release/0.1_test\` — аппаратно загружавшийся контрольный образ, но со старым неисправным Web UI; НЕ считать финальным релизом.

Не смешивать эти исходники. Для каждой новой функции создавать \`feature/*\` от \`main\`, затем PR → CI → review → merge в \`main\`. Веб-панель получит уведомление об обновлении; установка только по явному подтверждению в разделе «Система». Для следующего успешного обновления станет доступен откат на прежний SHA. **Не делать force push/reset основного репозитория**.

## Разрешённые изменения / защищённые зоны

| Модуль | Изменять для | Осторожность |
|---|---|---|
| \`templates/index.html\`, \`static/*\` | кнопки, тексты, таблицы, графики | не подключать внешние скрипты или скачивание секретов |
| \`build_metrics.py\` | ETA, таймлайн | не выдавать оценку за фактический % компиляции |
| \`artifact_checks.py\` | *отдельная проверка нового профиля* | T23N MSPL LBA34, p1=2048, p2=34816 — **не менять**, пока не появится аппаратно проверенный новый формат |
| \`git_sources.py\` | новые доверенные исходные репозитории | allowlist, изолированный worktree, SHA pin, не принимать arbitrary URLs |
| \`worker.py\` | новые профили и фазы сборки | \`PUBLISH=0\`, отдельный systemd unit, не трогать другие службы |
| \`core.py\` | история, SQL, миграции | не терять старые jobs, всегда совместимая migration |
| \`app.py\` | проверенные API действия | не принимать произвольные disk paths / shell commands |
| \`update_manager.py\` | обновления панели | ff-only, проверка busy, rollback без удаления SQLite/firmware |
| WIFICAM \`scripts/assemble_thingino_wificam_sd_image.sh\` | формат SD | bootloader/MSPL offset и recovery не изменять без hardware test |
| WIFICAM \`rootfs/\` и \`web/\` | сервисы и UI самой камеры | пересобрать image, проверить CGI, Wi-Fi, SSH, RTSP, PTZ на камере |
| \`local/wifi.env\` и \`out/private-sd/\` | персональные параметры | НИКОГДА не публиковать, не добавлять в docs/скриншоты |

Комментарии в исходниках теперь поясняют проверяемые адреса, ограничения прогресса, допустимые профили и область каждой операции. Если меняется формат SD другого SoC, создайте **новый профиль+валидатор+тестовые эталонные образы**, а не переписывайте T23N константы.

## Как изменить код

\`\`\`bash
# На рабочей машине — НЕ изменять прямо на Huananzhi, если нужна история
git clone https://github.com/musikfed/YadroKreator.git
cd YadroKreator
git switch -c feature/my-change main
# измените файлы и добавьте тест
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -p 'test_*.py' -v
python -m compileall -q app.py core.py worker.py git_sources.py artifact_checks.py build_metrics.py update_manager.py
bash -n bootstrap.sh install.sh deploy.sh setup-update-timer.sh
git add app.py static/ tests/ docs/   # перечислить только нужное
git commit -m "feat: describe safe change / описание изменения"
git push -u origin feature/my-change
# GitHub PR -> CI -> review -> merge в main
\`\`\`

После зелёного CI и merge зайти в **Система → Проверить обновления → Обновить панель**. Не прерывать сборку во время обновления, не чистить \`factory-state/\` и \`build/jobs/\`. Для ручного Git deploy: \`bash deploy.sh --check\`, затем \`bash deploy.sh --apply\` когда нет задач.

## Разделить типы релиза

**Релиз веб-панели**: исходники \`YadroKreator/main\`, unit/API/UI tests; контрольный SHA, deploy, rollback. Никакая SD-карта не затрагивается.

**Релиз прошивки камеры**:
1. Выбрать явный source SHA ветки WIFICAM; закреплённый Thingino commit и профиль \`galayou_g2_t23n_sc2336_atbm6012bx\`.
2. Собрать с \`PUBLISH=0\` в отдельном каталоге задачи; сохранить SHA, размер, логи и конфигурацию. Старый \`0.1_test\` неизменен.
3. Нажать **Проверить образ**: MBR+SHA+LBA34+FAT16 uImage+ext4. Это только offline image gate.
4. Вставить SD, убедиться в верном устройстве (\`lsblk\`); записать образ с **LBA0**, а не \`seek=34\`, с контролем SHA чтением.
5. Вставить карту в T23N и проверить питание, SD boot, SSH, видео, API CGI, Web UI \`:8090\`, PTZ, Wi-Fi и recovery.
6. Только после успешной аппаратной проверки оформить \`0.2_test\`: tag/release notes RU/EN, board/SoC, source SHA, Thingino SHA, image SHA, список проверенных функций и известные ошибки. Публичный релиз — **без персональных Wi-Fi настроек**.

## Зачем нужны скриншоты / схемы

Новые preview SVG лежат в \`docs/previews\` и пригодны для README, issues, code review. Они **макеты**, а не доказательство испытаний. Динамический SVG реального образа создаётся на сервере из его байтов только после preflight; скачивание приватного \`.bin\` через веб не допускается. Перед публикацией живого скриншота удалить SSID, PSK, токены, частные сетевые адреса при необходимости.

См. [дерево проекта](ARCHITECTURE_RU.md), [проверка перед SD](PREFLIGHT_RU.md), [git-деплой](GIT_DEPLOY_RU.md).
