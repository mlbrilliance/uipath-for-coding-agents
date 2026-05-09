using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.Json;
using AuroraSupplyChainDefender.Notify;
using UiPath.CodedWorkflows;
using Xunit;

namespace AuroraSupplyChainDefender.Notify.Tests;

/// <summary>
/// T-C7 regression contract: the BPMN End-event's BatchDigest service task
/// (Medium-severity path, "Batch into weekly digest") is bound to the
/// Notify.AppendToDigest coded workflow shipped by T-C4. This test loads
/// bindings.json, resolves the BatchDigest entry to the shipped class, and
/// asserts the I/O surface that BPMN promises matches what the class
/// actually exposes — so any future drift in either side fails fast.
/// </summary>
public class AppendToDigest_BatchContract_Tests
{
    private static string BindingsPath([CallerFilePath] string thisFile = "")
    {
        string testsDir = Path.GetDirectoryName(thisFile)!;
        return Path.GetFullPath(Path.Combine(
            testsDir, "..", "..", "..",
            "examples", "oss-supply-chain-defender", "bindings.json"));
    }

    private static JsonElement BatchDigestBinding()
    {
        string text = File.ReadAllText(BindingsPath());
        using JsonDocument doc = JsonDocument.Parse(text);
        JsonElement tasks = doc.RootElement.GetProperty("tasks");
        JsonElement entry = tasks.GetProperty("BatchDigest");
        return JsonDocument.Parse(entry.GetRawText()).RootElement;
    }

    [Fact]
    public void BatchDigest_Binding_Is_Coded_Workflow()
    {
        JsonElement binding = BatchDigestBinding();

        Assert.Equal("coded-workflow", binding.GetProperty("kind").GetString());
        Assert.Equal(
            "AuroraSupplyChainDefender",
            binding.GetProperty("package").GetString());
    }

    [Fact]
    public void BatchDigest_Resolves_To_Notify_AppendToDigest()
    {
        JsonElement binding = BatchDigestBinding();

        string entry = binding.GetProperty("entry").GetString()!;
        Assert.Equal("Notify.AppendToDigest", entry);

        string typeName = entry.Split('.').Last();
        Type? shipped = typeof(AppendToDigest).Assembly
            .GetTypes()
            .FirstOrDefault(t => t.Name == typeName);

        Assert.NotNull(shipped);
        Assert.Equal(typeof(AppendToDigest), shipped);
    }

    [Fact]
    public void Shipped_AppendToDigest_Has_Workflow_Entry_Method()
    {
        MethodInfo? execute = typeof(AppendToDigest).GetMethod(
            "Execute",
            BindingFlags.Instance | BindingFlags.Public);

        Assert.NotNull(execute);
        Assert.NotNull(execute!.GetCustomAttribute<WorkflowAttribute>());
    }

    [Fact]
    public void Execute_Accepts_Single_DigestEntry_And_Returns_Int_Size()
    {
        MethodInfo execute = typeof(AppendToDigest).GetMethod(
            "Execute",
            BindingFlags.Instance | BindingFlags.Public)!;

        ParameterInfo[] parameters = execute.GetParameters();
        Assert.Single(parameters);
        Assert.Equal(typeof(DigestEntry), parameters[0].ParameterType);
        Assert.Equal("in_objEntry", parameters[0].Name);
        Assert.Equal(typeof(int), execute.ReturnType);
    }

    [Fact]
    public void Binding_Inputs_Reference_Declared_Runtime_Variables()
    {
        string text = File.ReadAllText(BindingsPath());
        using JsonDocument doc = JsonDocument.Parse(text);
        JsonElement variables = doc.RootElement.GetProperty("variables");
        JsonElement binding = doc.RootElement
            .GetProperty("tasks")
            .GetProperty("BatchDigest");

        JsonElement inputs = binding.GetProperty("io").GetProperty("inputs");
        foreach (JsonProperty input in inputs.EnumerateObject())
        {
            string variableRef = input.Value.GetString()!;
            Assert.True(
                variables.TryGetProperty(variableRef, out _),
                $"BatchDigest input '{input.Name}' references undeclared variable '{variableRef}'");
        }
    }
}
