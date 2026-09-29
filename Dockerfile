# Runs the bot without installing a browser, a driver or Python on the host.
#
# The browser is Chromium rather than Edge: Edge has no Linux arm64 build, and
# Debian's chromium runs on both amd64 and arm64 (a Raspberry Pi, for one).
#
# The image carries only what main.py actually reaches: selenium, numpy,
# python-dotenv, requests, ollama and pillow. pygetwindow, keyboard, matplotlib and pygame are used solely by the
# recording and visualisation scripts, which are developer tools rather than
# part of a run, and two of them are Windows-only.
#
# QUERY_SOURCE defaults to trends here so a container needs no Ollama account
# and no model download. Set it to llm and point OLLAMA_HOST at a reachable
# host to use a model instead.

FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive

# Chromium and its driver from Debian. Edge has no Linux arm64 build, so it
# cannot be installed on a Raspberry Pi; Debian's chromium and chromium-driver
# come from the same source package and so always match each other.
RUN apt-get update \
	&& apt-get install -y --no-install-recommends \
		ca-certificates fonts-liberation chromium chromium-driver \
	&& rm -rf /var/lib/apt/lists/* \
	&& chromium --version && chromedriver --version

ENV CHROME_BINARY=/usr/bin/chromium \
	CHROMEDRIVER_PATH=/usr/bin/chromedriver

# Signing in needs a browser window, and the profile has to be written by the
# container's own Chromium: Chromium takes the cookie key from the operating system,
# and on a Windows or macOS host that key is wrapped with DPAPI or the login
# Keychain, neither of which the container can unwrap. Xvfb gives that browser a
# display and noVNC puts it on the user's screen with nothing installed on the
# host. Only src/signin.py reaches any of this; a run never does.
RUN apt-get update \
	&& apt-get install -y --no-install-recommends \
		xvfb x11vnc novnc websockify \
	&& rm -rf /var/lib/apt/lists/* \
	# Debian ships vnc.html and no index.html, so a bare localhost:6080 is a 404
	# that reads as the feature being broken.
	&& ln -s /usr/share/novnc/vnc.html /usr/share/novnc/index.html

WORKDIR /app

RUN pip install --no-cache-dir \
	"selenium>=4.46.0,<5.0.0" "numpy" "python-dotenv>=1.0.1,<2.0.0" \
	"requests>=2.32.3,<3.0.0" "ollama>=0.6.2,<0.7.0" "pillow>=12.3.0,<13.0.0"

COPY src/ ./src/
COPY nouns.txt ./

# Headless because there is no display, and trends because there is no model.
ENV REWARDS_HEADLESS=1 \
	QUERY_SOURCE=trends \
	PYTHONUNBUFFERED=1

# Sign-in lives here, so it has to outlive the container.
VOLUME ["/app/data-dir"]

CMD ["python", "src/main.py"]
