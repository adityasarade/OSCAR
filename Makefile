# OSCAR release Makefile
# Versions are read live from pyproject.toml and vscode-oscar/package.json.

ROOT       := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
VSCE_DIR   := $(ROOT)/vscode-oscar
PY_VERSION := $(shell awk -F'"' '/^version = /{print $$2; exit}' $(ROOT)/pyproject.toml)
VS_VERSION := $(shell node -p "require('$(VSCE_DIR)/package.json').version")
VSIX       := $(VSCE_DIR)/oscar-assistant-$(VS_VERSION).vsix
WHEEL_DIR  := $(ROOT)/dist

.PHONY: help versions test build-py build-vsce package clean \
        publish-pypi publish-pypi-test publish-vscode \
        tag push gh-release release release-dry preflight

help:
	@echo "OSCAR release targets:"
	@echo "  make versions          Show current artifact versions"
	@echo "  make preflight         Verify auth and tooling without changing anything"
	@echo "  make test              Run pytest + tsc typecheck"
	@echo "  make build-py          Build wheel + sdist into ./dist"
	@echo "  make build-vsce        Compile TS + package the .vsix"
	@echo "  make package           build-py + build-vsce"
	@echo "  make publish-pypi-test Publish to TestPyPI (requires UV_PUBLISH_TOKEN)"
	@echo "  make publish-pypi      Publish to PyPI (requires UV_PUBLISH_TOKEN)"
	@echo "  make publish-vscode    Publish to VS Code Marketplace (requires vsce login)"
	@echo "  make tag               Create local git tags for both versions"
	@echo "  make push              Push commits and tags to origin"
	@echo "  make gh-release        Create GitHub releases with attached artifacts"
	@echo "  make release           Full pipeline: test → package → publish → tag → push → gh-release"
	@echo "  make release-dry       Same pipeline but skips every publish/push step"
	@echo "  make clean             Remove built artifacts"

versions:
	@echo "oscar-agent       (PyPI)        $(PY_VERSION)"
	@echo "oscar-assistant   (Marketplace) $(VS_VERSION)"

preflight:
	@echo "== tooling =="
	@uv --version
	@node --version
	@cd $(VSCE_DIR) && npx --no-install vsce --version
	@gh --version | head -1
	@echo "== auth =="
	@if [ -n "$$UV_PUBLISH_TOKEN" ] || [ -f $$HOME/.pypirc ]; then echo "PyPI: token present"; else echo "PyPI: MISSING (set UV_PUBLISH_TOKEN or ~/.pypirc)"; fi
	@if [ -f $$HOME/.vsce ] || [ -n "$$VSCE_PAT" ]; then echo "vsce: credentials present"; else echo "vsce: MISSING (run 'npx vsce login adityasarade' or export VSCE_PAT)"; fi
	@gh auth status 2>&1 | head -3

test:
	cd $(ROOT) && uv run --extra dev pytest -q
	cd $(VSCE_DIR) && npx tsc --noEmit

build-py: clean
	cd $(ROOT) && uv build

build-vsce:
	cd $(VSCE_DIR) && npm install --no-fund --no-audit
	cd $(VSCE_DIR) && npm run compile
	cd $(VSCE_DIR) && npx vsce package --out $(VSIX)
	@echo "Built $(VSIX)"

package: build-py build-vsce

publish-pypi-test: build-py
	@if [ -z "$$UV_PUBLISH_TOKEN" ] && [ ! -f $$HOME/.pypirc ]; then \
		echo "ERROR: set UV_PUBLISH_TOKEN or configure ~/.pypirc"; exit 1; fi
	cd $(ROOT) && uv publish --publish-url https://test.pypi.org/legacy/

publish-pypi: build-py
	@if [ -z "$$UV_PUBLISH_TOKEN" ] && [ ! -f $$HOME/.pypirc ]; then \
		echo "ERROR: set UV_PUBLISH_TOKEN or configure ~/.pypirc"; exit 1; fi
	cd $(ROOT) && uv publish

publish-vscode: build-vsce
	@if [ ! -f $$HOME/.vsce ] && [ -z "$$VSCE_PAT" ]; then \
		echo "ERROR: run 'npx vsce login adityasarade' or export VSCE_PAT"; exit 1; fi
	cd $(VSCE_DIR) && npx vsce publish --packagePath $(VSIX)

tag:
	@if git rev-parse oscar-agent-v$(PY_VERSION) >/dev/null 2>&1; then \
		echo "tag oscar-agent-v$(PY_VERSION) already exists"; else \
		git tag oscar-agent-v$(PY_VERSION); fi
	@if git rev-parse vscode-v$(VS_VERSION) >/dev/null 2>&1; then \
		echo "tag vscode-v$(VS_VERSION) already exists"; else \
		git tag vscode-v$(VS_VERSION); fi

push:
	git push origin HEAD
	git push origin --tags

gh-release: package
	gh release create oscar-agent-v$(PY_VERSION) \
		--title "oscar-agent v$(PY_VERSION)" \
		--generate-notes \
		$(WHEEL_DIR)/oscar_agent-$(PY_VERSION)-py3-none-any.whl \
		$(WHEEL_DIR)/oscar_agent-$(PY_VERSION).tar.gz
	gh release create vscode-v$(VS_VERSION) \
		--title "oscar-assistant v$(VS_VERSION)" \
		--generate-notes \
		$(VSIX)

release: test package publish-pypi publish-vscode tag push gh-release
	@echo "Released oscar-agent v$(PY_VERSION) and oscar-assistant v$(VS_VERSION)."

release-dry: test package tag
	@echo "Dry release done. Artifacts in $(WHEEL_DIR) and $(VSIX). Skipped publish + push + gh-release."

clean:
	rm -rf $(WHEEL_DIR) $(ROOT)/build $(ROOT)/*.egg-info
	rm -f $(VSCE_DIR)/oscar-assistant-*.vsix
