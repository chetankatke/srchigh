.PHONY: install install-dev test build clean uninstall

# Install package in editable mode
install:
	pip3 install -r requirements.txt
	pip3 install -e .

# Install dev/test dependencies
install-dev: install
	pip3 install pytest

# Run tests
test:
	cd src && python3 -m pytest ../tests/ -v

# Build pip package (tar.gz + wheel)
build:
	pip3 install build
	python3 -m build

# Build standalone binary with PyInstaller
binary:
	pip3 install pyinstaller
	pyinstaller --onefile --name srchigh \
		--add-data "src/srchigh:srchigh" \
		src/srchigh/main.py
	@echo "Binary: dist/srchigh"

# Clean build artifacts
clean:
	rm -rf build/ dist/ *.egg-info/ __pycache__/ .pytest_cache/
	find . -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true

# Full uninstall
uninstall:
	pip3 uninstall srchigh -y 2>/dev/null || true
