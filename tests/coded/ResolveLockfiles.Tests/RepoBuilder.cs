using System.Reflection;
using Octokit;

namespace AuroraSupplyChainDefender.GitHub.Tests
{
    /// <summary>
    /// Octokit's <see cref="Repository"/> has a parameterless constructor but
    /// private setters. Tests need only Name / FullName / Owner.Login, so we
    /// poke those via reflection instead of calling the 50-arg constructor.
    /// </summary>
    internal static class RepoBuilder
    {
        public static Repository Make(string ownerLogin, string name)
        {
            var user = new User();
            SetProp(user, nameof(User.Login), ownerLogin);

            var repo = new Repository();
            SetProp(repo, nameof(Repository.Name), name);
            SetProp(repo, nameof(Repository.FullName), $"{ownerLogin}/{name}");
            SetProp(repo, nameof(Repository.Owner), user);
            return repo;
        }

        private static void SetProp(object target, string propName, object value)
        {
            var prop = target.GetType().GetProperty(
                propName,
                BindingFlags.Public | BindingFlags.Instance);
            prop!.GetSetMethod(nonPublic: true)!.Invoke(target, new[] { value });
        }
    }
}
