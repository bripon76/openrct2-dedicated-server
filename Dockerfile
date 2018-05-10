FROM ubuntu:16.04

RUN apt-get update && apt-get install -y \
		git \
		cmake \
		libsdl2-dev \
		gcc pkg-config \
		libjansson-dev \
		libspeex-dev \
		libspeexdsp-dev \
		libcurl4-openssl-dev \
		libcrypto++-dev \
		libfontconfig1-dev \
		libfreetype6-dev \
		libpng-dev \
		libssl-dev \
		libzip-dev \
	&& rm -rf /var/lib/apt/lists/*

RUN mkdir -p /openrct2/config /openrct2/original_files \ 
	&& git clone --branch v0.1.2 https://github.com/OpenRCT2/OpenRCT2.git /openrct2/src \
	&& mkdir /openrct2/src/build \
	&& cmake -B/openrct2/src/build -H/openrct2/src \
	&& make -C /openrct2/src/build -j8 \
	&& make -C /openrct2/src/build g2 -j8 \
	&& ln -s /openrct2/src/data /openrct2/src/build/data \
	&& ln -s /openrct2/src/build/g2.dat /openrct2/src/data/g2.dat

VOLUME /openrct2/config
VOLUME /openrct2/original_files

EXPOSE 11753

CMD /openrct2/src/build/openrct2 host /openrct2/game.sc6 --port 11753 --headless --verbose
