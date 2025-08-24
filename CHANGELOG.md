# Changelog

All notable changes to this project will be documented in this file. See [standard-version](https://github.com/conventional-changelog/standard-version) for commit guidelines.

## [2.0.0](https://github.com/tks18/open-memory-lane/compare/v1.0.0...v2.0.0) (2025-08-24)


### Features 🔥

* **app/workers:** write worker classes for capture, backup, db_writer, client ([ac0ae68](https://github.com/tks18/open-memory-lane/commit/ac0ae6835f7e05447d728f3e3f245f8420fc1651))
* **client:** integrated client as part of the single app ([08bc537](https://github.com/tks18/open-memory-lane/commit/08bc537dae9a6bf5c6d66eb0453d5fd0ec2bc39d))
* **helpers/{paths, win}:** write all helpers for paths & windows ([8d0ebdf](https://github.com/tks18/open-memory-lane/commit/8d0ebdfb977abb3a0446f306000e4911053391e5))
* **helpers/config:** rewrite configs to a seperate module for easier imports ([34d8c79](https://github.com/tks18/open-memory-lane/commit/34d8c79479a27718086cc60217223190150f038c))
* **helpers/copy:** write all copy helpers in a single file ([3d9c20f](https://github.com/tks18/open-memory-lane/commit/3d9c20fca470e3733380e62648c6832a01b13e96))
* **helpers/db:** write all db helper functions in a module ([fc4e233](https://github.com/tks18/open-memory-lane/commit/fc4e23370c906e72cd0a38bd2492000389da120e))
* **helpers/general:** write all common helper functions ([4a9b635](https://github.com/tks18/open-memory-lane/commit/4a9b635f42a9de70aa6a9621bf7be3ac49da510f))
* **helpers/lockfile:** write all lockfile related helpers ([5f088b2](https://github.com/tks18/open-memory-lane/commit/5f088b2b8df439a053312e497fad9fe5459e9d40))
* **helpers/screencapture:** completely rewrite the screenshot module using opencv using dhash ([59c257a](https://github.com/tks18/open-memory-lane/commit/59c257a0765f5fe7cf4939d6153a5cc75857d56c))
* **helpers/video:** write all video related helpers ([57c1bd7](https://github.com/tks18/open-memory-lane/commit/57c1bd71f12f42c5e3a81d92567a37eefbf42c99))
* **logger:** write a logger function using queue based approach ([4f15bc7](https://github.com/tks18/open-memory-lane/commit/4f15bc74d1d35894711def6fdce01b31d741ebea))
* **workers/video:** write a new video worker so that it doesnt block captures ([1746bc1](https://github.com/tks18/open-memory-lane/commit/1746bc12ddc45f34314641bd832c1e68e476b4f0))


### Code Refactoring 🖌

* **app/db:** write all common sql statements in a single file ([1ba5dab](https://github.com/tks18/open-memory-lane/commit/1ba5dabd8c918682475c2452264b45e930eb467c))
* **app:** refactor the app completely with module based approach ([3b54dca](https://github.com/tks18/open-memory-lane/commit/3b54dcadfdf63cfb4327498653e8bfa09ba6bc38))


### CI 🛠

* **project_config:** updated packages for the env ([a2b3b15](https://github.com/tks18/open-memory-lane/commit/a2b3b15f9ce07a0be412825fe1d175db663af58a))


### Others 🔧

* **changelog:** remove null version ([475b981](https://github.com/tks18/open-memory-lane/commit/475b981deecc4ff0346f1cc1c8c3ef1036baf6f0))
* **dev:** checkout dev branch ([2ca96da](https://github.com/tks18/open-memory-lane/commit/2ca96da65207ed42077ba20c6ab0088d869f42a8))
* **package.json:** update command for git push ([0c3326f](https://github.com/tks18/open-memory-lane/commit/0c3326f5fe80d7cce3bbdc035d2ca9137a221f33))

## 1.0.0 (2025-08-23)


### Bug Fixes 🛠

* backlog dont process current session ([6ce7370](https://github.com/tks18/open-memory-lane/commit/6ce73701b4c1d3dc88ff5c1e60ade72671f8ec3e))
* logger paths & add logger path to the app_starter ([20a338d](https://github.com/tks18/open-memory-lane/commit/20a338dc25e9e9c534fa240089ea39670970d298))


### Features 🔥

* **app:** intialize commitlint, version-management & changelog management ([f1537aa](https://github.com/tks18/open-memory-lane/commit/f1537aa00e0e72172547f7d4b1606c5247feed07))
* make a backup worker to upload to cloud, update lock algorithm, organize folder properly, update the similar changes to client ([575e622](https://github.com/tks18/open-memory-lane/commit/575e622277b6da6e5dcc7199089a0e2b0027f8b7))
* update db schema to support archival, archive db periodically and gracefully ([cb5c12b](https://github.com/tks18/open-memory-lane/commit/cb5c12b1057828dbe5a3bc0b1f541b708e3d34d1))


### Others 🔧

* **release:** null ([721ccb6](https://github.com/tks18/open-memory-lane/commit/721ccb6a082210193e45dab0fbb31bb846344317))

##  (2025-08-23)


### Bug Fixes 🛠

* backlog dont process current session ([6ce7370](https://github.com/tks18/open-memory-lane/commit/6ce73701b4c1d3dc88ff5c1e60ade72671f8ec3e))
* logger paths & add logger path to the app_starter ([20a338d](https://github.com/tks18/open-memory-lane/commit/20a338dc25e9e9c534fa240089ea39670970d298))


### Features 🔥

* **app:** intialize commitlint, version-management & changelog management ([f1537aa](https://github.com/tks18/open-memory-lane/commit/f1537aa00e0e72172547f7d4b1606c5247feed07))
* make a backup worker to upload to cloud, update lock algorithm, organize folder properly, update the similar changes to client ([575e622](https://github.com/tks18/open-memory-lane/commit/575e622277b6da6e5dcc7199089a0e2b0027f8b7))
* update db schema to support archival, archive db periodically and gracefully ([cb5c12b](https://github.com/tks18/open-memory-lane/commit/cb5c12b1057828dbe5a3bc0b1f541b708e3d34d1))
