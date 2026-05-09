// AURORA contract-test fixture (NOT a real workflow).
//
// Encodes the shape forger-coded promises (R.N.04, R.N.02, R.K.02, R.L.03).

using System.Threading.Tasks;
using UiPath.CodedWorkflows;

namespace AuroraSupplyChainDefender.GitHub.FetchLockfile
{
    public class FetchLockfile : CodedWorkflowBase
    {
        [Workflow]
        public async Task<LockfileResult> Execute(string in_strRepoName, string in_strBranch)
        {
            Log.Information("Starting {Action} for {Repo}", nameof(FetchLockfile), in_strRepoName);

            var out_strLockfilePath = await _client.FetchAsync(in_strRepoName, in_strBranch);

            Log.Information("Completed {Action}", nameof(FetchLockfile));
            return new LockfileResult(out_strLockfilePath);
        }
    }
}
