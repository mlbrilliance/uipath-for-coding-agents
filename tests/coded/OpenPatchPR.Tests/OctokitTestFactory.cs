using System;
using System.Reflection;
using Octokit;

namespace AuroraSupplyChainDefender.GitHub.Tests;

/// <summary>
/// Octokit's response models (<see cref="Repository"/>, <see cref="Reference"/>,
/// <see cref="PullRequest"/>, <see cref="RepositoryContent"/>) ship with
/// non-public property setters — which makes total sense in production (the
/// API hands back immutable views) but is hostile to unit tests, where the
/// mock has to assemble a realistic response.
/// </summary>
/// <remarks>
/// The helpers here use <see cref="BindingFlags.NonPublic"/> reflection to
/// reach the protected setter and seed only the fields the tests assert on.
/// All methods are pure: they return a new instance each call.
/// </remarks>
internal static class OctokitTestFactory
{
    public static Repository MakeRepository(string defaultBranch)
    {
        var r = new Repository();
        SetProp(r, nameof(Repository.DefaultBranch), defaultBranch);
        return r;
    }

    public static Reference MakeReference(string sha)
    {
        var tag = new TagObject();
        SetProp(tag, nameof(TagObject.Sha), sha);

        var reference = new Reference();
        SetProp(reference, nameof(Reference.Object), tag);
        SetProp(reference, nameof(Reference.Ref), "refs/heads/test");
        return reference;
    }

    public static PullRequest MakePullRequest(int number, string htmlUrl)
    {
        var pr = new PullRequest();
        SetProp(pr, nameof(PullRequest.Number), number);
        SetProp(pr, nameof(PullRequest.HtmlUrl), htmlUrl);
        return pr;
    }

    public static RepositoryContent MakeRepositoryContent(string sha)
    {
        var content = new RepositoryContent();
        SetProp(content, nameof(RepositoryContent.Sha), sha);
        return content;
    }

    private static void SetProp(object target, string name, object? value)
    {
        PropertyInfo? prop = target.GetType().GetProperty(
            name,
            BindingFlags.Instance | BindingFlags.Public);
        if (prop is null)
        {
            throw new MissingMemberException(target.GetType().FullName, name);
        }
        MethodInfo? setter = prop.GetSetMethod(nonPublic: true);
        if (setter is null)
        {
            throw new MissingMethodException(target.GetType().FullName, "set_" + name);
        }
        setter.Invoke(target, new[] { value });
    }
}
