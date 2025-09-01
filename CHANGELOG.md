# Changelog

All notable changes to this project will be documented in this file. See [standard-version](https://github.com/conventional-changelog/standard-version) for commit guidelines.

## [2.3.0](https://github.com/tks18/open-memory-lane/compare/v2.2.0...v2.3.0) (2025-09-01)


### Bug Fixes 🛠

* **helpers/client:** fix the downsample function to return exact linspaced items ([6990c0c](https://github.com/tks18/open-memory-lane/commit/6990c0ccee4cf5da68df0ea54500760da5c625b5))


### Features 🔥

* **helpers/copy:** use a new manifest way of checking the backup location and skip copying ([7331041](https://github.com/tks18/open-memory-lane/commit/733104171a9f204ed0c3137711631a38d2b65c05))
* **helpers/screenshot:** add window_title & app_name to the overlay, also change the position ([12e3d16](https://github.com/tks18/open-memory-lane/commit/12e3d1669609948beffb4f5db6c47eed9a0caa50))


### Code Refactoring 🖌

* refactor of code (prettier) ([eac732f](https://github.com/tks18/open-memory-lane/commit/eac732f67dbe04c2965f826a677eb503c6dccbed))


### Docs 📃

* add all docstrings for all the remaining functions, classes ([7bea3e8](https://github.com/tks18/open-memory-lane/commit/7bea3e888dfca958c7635a4292e40374e9a1c6a8))
* add documentations to most of the functions, modules, workers ([b98cc5c](https://github.com/tks18/open-memory-lane/commit/b98cc5c60f65ba32a50df14a0b796fe795790af7))
* fix docs ([8feb34c](https://github.com/tks18/open-memory-lane/commit/8feb34c71a6f360ecd297d5e0efbf4afe16d4318))
* **readme:** update readme file for client related details ([83f0088](https://github.com/tks18/open-memory-lane/commit/83f00881305bd7e699d2b397e013fa179c861e11))
* update readme ([6108a06](https://github.com/tks18/open-memory-lane/commit/6108a06d684068467bf2f227ab7def43b3e7890e))

## [2.2.0](https://github.com/tks18/open-memory-lane/compare/v2.1.1...v2.2.0) (2025-08-27)


### Bug Fixes 🛠

* **helpers/video:** more optimizations for the video creations ([ef25182](https://github.com/tks18/open-memory-lane/commit/ef251829a85226d05f4b8c30a4d2df2fca02424a))


### Docs 📃

* **readme:** update readme ([5ce6c3e](https://github.com/tks18/open-memory-lane/commit/5ce6c3e73f124aef06efce9b3f0edec959884825))

### [2.1.1](https://github.com/tks18/open-memory-lane/compare/v2.1.0...v2.1.1) (2025-08-27)


### Bug Fixes 🛠

* **helpers/video:** optimizations for ffmpeg to build the video faster ([e756660](https://github.com/tks18/open-memory-lane/commit/e75666050e270beadbda3e975c96b401af6874ec))

## [2.1.0](https://github.com/tks18/open-memory-lane/compare/v2.0.0...v2.1.0) (2025-08-26)


### Features 🔥

* **screenshot:** add overlay of timestamp to the screenshot ([965044c](https://github.com/tks18/open-memory-lane/commit/965044ccfd9beec48ce9c47ade2a3f424b81fd5a))


### Code Refactoring 🖌

* **logger:** added proper logging to the workers ([271dc55](https://github.com/tks18/open-memory-lane/commit/271dc551b546d7edb33e99049ec55d537bcecc4e))
* rename the var names for proper documentation ([dbb1fdb](https://github.com/tks18/open-memory-lane/commit/dbb1fdb16b0e2193d731672ab50ead6f7d1442fe))


### Bug Fixes 🛠

* **sql:** fix the sql statement for insert summary row ([50d5ce2](https://github.com/tks18/open-memory-lane/commit/50d5ce28b222ab4d05bade62399ac24db7bd6ec1))
* **start_script:** fix the start script to refer the correct start file ([e5707da](https://github.com/tks18/open-memory-lane/commit/e5707da01c88fe7bf79ff74513c820a00d6b1a1a))


### CI 🛠

* **configs:** edited config, package.json for commit ci ([f8773ec](https://github.com/tks18/open-memory-lane/commit/f8773ec28a78544c78a1d5ed74391daa17f1c461))

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
