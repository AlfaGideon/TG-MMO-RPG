{ pkgs }: {
  deps = [
    pkgs.python311
    pkgs.python311Packages.pip
    pkgs.git
    pkgs.libpng
    pkgs.libjpeg
    pkgs.zlib
    pkgs.freetype
  ];
}
