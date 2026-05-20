# nix/overlays.nix — Expose pkgs.aot-agent for external NixOS configs
{ inputs, ... }:
{
  flake.overlays.default = final: _: {
    aot-agent = final.callPackage ./aot-agent.nix {
      inherit (inputs) uv2nix pyproject-nix pyproject-build-systems;
      npm-lockfile-fix = inputs.npm-lockfile-fix.packages.${final.stdenv.hostPlatform.system}.default;
      rev = inputs.self.rev or null;
    };
  };
}
