// Minimal UnityEngine shim so the vendored bfxr synthesiser can run outside Unity.
// Only the two primitives this code actually touches are provided:
//   UnityEngine.Mathf.{Abs,Clamp,Epsilon,Floor,Max,Min,PI,Pow,RoundToInt,Sin,Tan}
//   UnityEngine.Random.value
// The bfxr algorithm itself is untouched (see src/SfxrGenerator.cs et al).
using System;

namespace UnityEngine
{
    public static class Mathf
    {
        public const float Epsilon = 1e-5f;
        public const float PI = 3.14159274f;

        public static float Abs(float v) => Math.Abs(v);
        public static float Clamp(float v, float a, float b) => v < a ? a : (v > b ? b : v);
        public static int Clamp(int v, int a, int b) => v < a ? a : (v > b ? b : v);
        public static float Floor(float v) => (float)Math.Floor(v);
        public static float Max(float a, float b) => Math.Max(a, b);
        public static int Max(int a, int b) => Math.Max(a, b);
        public static float Max(params float[] values)
        {
            var m = values.Length > 0 ? values[0] : 0f;
            for (var i = 1; i < values.Length; i++) m = Math.Max(m, values[i]);
            return m;
        }
        public static int Max(params int[] values)
        {
            var m = values.Length > 0 ? values[0] : 0;
            for (var i = 1; i < values.Length; i++) m = Math.Max(m, values[i]);
            return m;
        }
        public static float Min(float a, float b) => Math.Min(a, b);
        public static int Min(int a, int b) => Math.Min(a, b);
        public static float Pow(float a, float b) => (float)Math.Pow(a, b);
        public static int RoundToInt(float v) => (int)Math.Round(v);
        public static float Sin(float v) => (float)Math.Sin(v);
        public static float Tan(float v) => (float)Math.Tan(v);
    }

    public static class Debug
    {
        public static void Log(object message) { }
        public static void LogWarning(object message) { }
        public static void LogError(object message) { Console.Error.WriteLine(message); }
    }

    public static class Random
    {
        [ThreadStatic] private static System.Random _r;
        private static System.Random R => _r ??= new System.Random(20261030);

        public static float value => (float)R.NextDouble();
        public static void InitState(int seed) => _r = new System.Random(seed);
    }
}
