# nix/packages.nix — Aot Agent package built with uv2nix
{ inputs, ... }:
{
  perSystem =
    { pkgs, inputs', ... }:
    let
      aotAgent = pkgs.callPackage ./aot-agent.nix {
        inherit (inputs) uv2nix pyproject-nix pyproject-build-systems;
        npm-lockfile-fix = inputs'.npm-lockfile-fix.packages.default;
        # Only embed clean revs — dirtyRev doesn't represent any upstream
        # commit, so comparing it would always claim "update available".
        rev = inputs.self.rev or null;
      };
    in
    {
      packages = {
        default = aotAgent;
        tui = aotAgent.aotTui;
        web = aotAgent.aotWeb;

        fix-lockfiles = aotAgent.aotNpmLib.mkFixLockfiles {
          packages = [ aotAgent.aotTui aotAgent.aotWeb ];
        };
      };
    };
}
